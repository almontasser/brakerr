from datetime import datetime

import httpx
import threading
import traceback
import qbittorrentapi
import time

from helpers.log_loader import logger
from helpers import arguments, log_loader


class QBittorrentClient:
    def __init__(self, url: str, username: str, password: str, verify_https: bool) -> None:
        self._url = url

        self._client = qbittorrentapi.Client(
            host=url,
            username=username,
            password=password,
            FORCE_SCHEME_FROM_HOST=True,
            VERIFY_WEBUI_CERTIFICATE=verify_https
        )

        logger.debug(f"<qbit|{url}> Connecting to qBittorrent at {url}")

        try:
            self._client.auth_log_in()

        except qbittorrentapi.LoginFailed:
            raise Exception(f"<qbit|{url}> Failed to login to qBittorrent, check your credentials")

        except qbittorrentapi.Forbidden403Error:
            raise Exception(f"<qbit|{url}> Failed to login to qBittorrent, temporarily banned, try again later")

        logger.debug(f"<qbit|{url}> Connected to qBittorrent")

    def set_download_speed(self, speed: int) -> None:
        """Set the download speed limit for the client, in bytes."""

        logger.debug(f"<qbit|{self._url}> Setting download speed to {speed} KBits")
        self._client.transfer_set_download_limit(int(speed) * 1024)


class JellyfinServer(threading.Thread):
    def __init__(self, url: str, api_key: str, update_interval: int, ignore_paused_after: int, verify_https: bool,
                 update_event: threading.Event) -> None:
        threading.Thread.__init__(self)

        self._api_key = api_key
        self._ignore_paused_after = int(ignore_paused_after)
        self._update_interval = int(update_interval)
        self._update_event = update_event

        self._client = httpx.Client(
            base_url=url,
            verify=verify_https
        )

        self._paused_since: dict[str, int] = {}

        self._logger_prefix = f"<jellyfin|{url}>"

        self._active_session = False
        self._streaming = False

        self._prev_active_session = False
        self._prev_streaming = False

    def remove_old_paused(self, active_session_ids: list[str]) -> None:
        for session_id in self._paused_since.copy():  # Copy to prevent RuntimeError: dictionary changed size during iteration
            if session_id not in active_session_ids:
                logger.debug(
                    f"{self._logger_prefix} Removing {session_id} from paused_since, no longer in session list")
                del self._paused_since[session_id]

    def process_sessions(self) -> None:
        """Get the active sessions from Jellyfin."""

        logger.debug(f"{self._logger_prefix} Getting sessions")

        res = self._client.get("/Sessions", headers={"Authorization": f'MediaBrowser Token="{self._api_key}"'})

        logger.debug(f"{self._logger_prefix} Got {res.status_code} response from Jellyfin")

        res.raise_for_status()

        res_json: list[dict] = res.json()

        session_ids: list[str] = []

        self._active_session = False
        self._streaming = False

        for session in res_json:
            session_id = session["Id"]
            last_activity = session["LastActivityDate"]
            username = session["UserName"]

            # last_activity is in the format 2024-11-04T08:45:39.9536253Z
            # Set active session to True if the session last activity is within the ignore_paused_after time
            if self._ignore_paused_after != -1:
                last_activity_time = datetime.fromisoformat(last_activity).timestamp()
                logger.debug(f"{self._logger_prefix} {username}:{session_id} last activity: {last_activity_time}")
                if int(time.time() - last_activity_time) < self._ignore_paused_after:
                    self._active_session = True

            if session.get("NowPlayingItem"):  # Ignore sessions that aren't playing anything
                paused = session["PlayState"]["IsPaused"]
                title = session["NowPlayingItem"]["Name"]
                session_ids.append(session_id)

                if paused and self._ignore_paused_after != -1:
                    if session_id not in self._paused_since:
                        self._paused_since[session_id] = int(time.time())
                        logger.debug(f"{self._logger_prefix} {title}:{session_id} is paused, noted time")
                        self._streaming = True
                    elif int(time.time()) - self._paused_since[session_id] > self._ignore_paused_after:
                        logger.debug(f"{self._logger_prefix} {title}:{session_id} paused for too long")
                    else:
                        self._streaming = True

                elif self._ignore_paused_after != -1:
                    self._streaming = True
                    if session_id in self._paused_since:
                        logger.debug(
                            f"{self._logger_prefix} {title}:{session_id} is no longer paused, removing from paused dict")
                        del self._paused_since[session_id]
                else:
                    self._streaming = True

        self.remove_old_paused(session_ids)

    def run(self) -> None:
        while True:
            try:
                self.process_sessions()
            except Exception:
                logger.error(f"{self._logger_prefix} Error getting bandwidth:\n" + traceback.format_exc())
            else:
                if self._streaming != self._prev_streaming or self._active_session != self._prev_active_session:
                    self._prev_active_session = self._active_session
                    self._prev_streaming = self._streaming
                    self._update_event.set()

            time.sleep(self._update_interval)

    @property
    def streaming(self):
        return self._streaming

    @property
    def active_session(self):
        return self._active_session


def main():
    args = arguments.load_args()

    log_loader.file_handler.setLevel(args.log_file_level)
    log_loader.stdout_handler.setLevel(args.log_level)

    logger.info("Starting Brakerr")

    update_event = threading.Event()

    qbittorrent = QBittorrentClient(args.qbit_url, args.qbit_username, args.qbit_password, args.qbit_verify_https)

    jellyfin = JellyfinServer(args.jellyfin_url, args.jellyfin_api_key, args.jellyfin_update_interval,
                              args.jellyfin_ignore_paused_after, args.jellyfin_verify_https, update_event)

    jellyfin.daemon = True
    jellyfin.start()

    # Force an initial update
    update_event.set()

    while True:
        # Without a timeout, Ctrl+C won't work.
        # Polling isn't great, but it will work.
        event_triggered = update_event.wait(timeout=0.2)
        if not event_triggered:
            continue

        # Clear immediately, so that the next event can be set.
        update_event.clear()

        logger.info("Update event triggered")

        if jellyfin.streaming:
            qbittorrent.set_download_speed(args.qbit_speed_limit)
            logger.info(f"Streaming detected, setting Speed to {args.qbit_speed_limit} KBits")
        elif jellyfin.active_session:
            qbittorrent.set_download_speed(args.qbit_speed_limit_paused)
            logger.info(f"Active session detected, setting Speed to {args.qbit_speed_limit_paused} KBits")
        else:
            qbittorrent.set_download_speed(0)
            logger.info(f"No active sessions, setting Speed to 0 KBits")

        logger.info("Download speeds updated")
        logger.info("Waiting for next update event")


if __name__ == '__main__':
    main()