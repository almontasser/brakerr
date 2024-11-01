import httpx
import threading
from typing import Union, List
import traceback
import qbittorrentapi
import time

from helpers.log_loader import logger
from helpers import arguments, log_loader


class qBittorrentClient:
    def __init__(self, url: str, username: str, password: str, verify_https: bool) -> None:
        self._url = url
        
        self._client = qbittorrentapi.Client(
            host = url,
            username = username,
            password = password,
            FORCE_SCHEME_FROM_HOST = True,
            VERIFY_WEBUI_CERTIFICATE = verify_https
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
        "Set the upload speed limit for the client, in bytes."
        
        logger.debug(f"<qbit|{self._url}> Setting upload speed to {speed}KBits")
        self._client.transfer_set_upload_limit(speed * 1024)
        
class JellyfinServer(threading.Thread):
    def __init__(self, url: str, api_key: str, update_interval: int, ignore_paused_after: int, verify_https: bool, update_event: threading.Thread) -> None:
        self._api_key = api_key
        self._ignore_paused_after = ignore_paused_after
        self._update_interval = update_interval
        self._update_event = update_event
        
        self._client = httpx.Client(
            base_url=url,
            verify=verify_https
        )
        
        self._paused_since: dict[str, int] = {}
        
        self._logger_prefix = f"<jellyfin|{url}>"
        
        self._streaming = False
        self._active_sessions = False
        
        self._prev_streaming = False
        self._prev_active_sessions = False
        
    def remove_old_paused(self, active_session_ids: list[str]) -> None:
        for session_id in self._paused_since.copy(): # Copy to prevent RuntimeError: dictionary changed size during iteration
            if session_id not in active_session_ids:
                logger.debug(f"{self._logger_prefix} Removing {session_id} from paused_since, no longer in session list")
                del self._paused_since[session_id]
        
    def process_sessions(self) -> None:
        "Get the active sessions from Jellyfin."
        
        logger.debug(f"{self._logger_prefix} Getting sessions")
        
        res = self._client.get("/Sessions", headers={"Authorization": f'MediaBrowser Token="{self._api_key}"'})

        logger.debug(f"{self._logger_prefix} Got {res.status_code} response from Jellyfin")
        
        res.raise_for_status()
        
        res_json: list[dict] = res.json()
        
        session_ids: list[str] = []
        
        
        for session in res_json:
            if session.get("NowPlayingItem"): # Ignore sessions that aren't playing anything
                session_id = session["Id"]
                paused = session["PlayState"]["IsPaused"]
                session_id  = session["Id"]
                title       = session["NowPlayingItem"]["Name"]
                                
                session_ids.append(session_id)
                
                
                if paused and self._ignore_paused_after != -1:
                    if session_id not in self._paused_since:
                        self._paused_since[session_id] = int(time.time())
                        logger.debug(f"{self._logger_prefix} {title}:{session_id} is paused, noted time")
                        self._active_sessions = True
                    elif int(time.time()) - self._paused_since[session_id] > self._ignore_paused_after:
                        logger.debug(f"{self._logger_prefix} {title}:{session_id} paused for too long")
                        
                elif self._ignore_paused_after != -1:
                    if session_id in self._paused_since:
                        logger.debug(f"{self._logger_prefix} {title}:{session_id} is no longer paused, removing from paused dict")
                        del self._paused_since[session_id]
                        
                if not paused:
                    self._active_sessions = True
                    self._streaming = True
                    logger.debug(f"{self._logger_prefix} {title}:{session_id} is streaming")
                
        self.remove_old_paused(session_ids)

    def run(self) -> None:
        while True:
            try:
                self.process_sessions()
            except Exception:
                logger.error(f"{self._logger_prefix} Error getting bandwidth:\n" + traceback.format_exc())
            else:
                if self._streaming != self._prev_streaming or self._active_sessions != self._prev_active_sessions:
                    self._prev_streaming = self._streaming
                    self._prev_active_sessions = self._active_sessions
                    self._update_event.set()
                    
            
            time.sleep(self._update_interval)


if __name__ == '__main__':
    args = arguments.load_args()
    
    log_loader.file_handler.setLevel(args.log_file_level)
    log_loader.stdout_handler.setLevel(args.log_level)


    logger.info("Starting Brakerr")
    
    update_event = threading.Event()
    
    qbittorrent = qBittorrentClient(args.qbit_url, args.qbit_username, args.qbit_password, args.qbit_verify_https)
    
    jellyfin = JellyfinServer(args.jellyfin_url, args.jellyfin_api_key, args.jellyfin_update_interval, args.jellyfin_ignore_paused_after, args.jellyfin_verify_https, update_event)
    
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
        
        if jellyfin._streaming:
            qbittorrent.set_download_speed(args.qbit_streaming_sessions_limit)
        elif jellyfin._active_sessions:
            qbittorrent.set_download_speed(args.qbit_active_sessions_limit)
        else:
            qbittorrent.set_download_speed(0)
        
        logger.info("Upload speeds updated")
        logger.info("Waiting for next update event")