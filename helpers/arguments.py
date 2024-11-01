import argparse
import os
import logging


def is_valid_file(parser: argparse.ArgumentParser, arg) -> str:
    if not os.path.exists(arg):
        parser.error(f"invalid path {arg}")
    else:
        return str(arg)

def load_args() -> argparse.Namespace:
    argparser = argparse.ArgumentParser()

    argparser.add_argument(
        '--qbit_url',
        dest='qbit_url',
        help='Url for qBittorrent',
        type=str,
        default=os.environ.get('BRAKERR_QBIT_URL')
    )
    argparser.add_argument(
        '--qbit_verify_https',
        dest='qbit_verify_https',
        help='Verify that the connection to qBittorrent is secure',
        type=bool,
        default=os.environ.get('BRAKERR_QBIT_VERIFY_HTTPS')
    )
    argparser.add_argument(
        '--qbit_username',
        dest='qbit_username',
        help='Username for qBittorrent',
        type=str,
        default=os.environ.get('BRAKERR_QBIT_USERNAME')
    )
    argparser.add_argument(
        '--qbit_password',
        dest='qbit_password',
        help='Password for qBittorrent',
        type=str,
        default=os.environ.get('BRAKERR_QBIT_PASSWORD')
    )
    argparser.add_argument(
        '--qbit_speed_limit',
        dest='qbit_speed_limit',
        help='Limit when there is streaming sessions',
        type=str,
        default=os.environ.get('BRAKERR_QBIT_SPEED_LIMIT')
    )
    
    argparser.add_argument(
        '--jellyfin_url',
        dest='jellyfin_url',
        help='Jellyfin server url',
        type=str,
        default=os.environ.get('BRAKERR_JELLYFIN_URL')
    )
    argparser.add_argument(
        '--jellyfin_verify_https',
        dest='jellyfin_verify_https',
        help='Verify that the connection to Jellyfin is secure',
        type=bool,
        default=os.environ.get('BRAKERR_JELLYFIN_VERIFY_HTTPS')
    )
    argparser.add_argument(
        '--jellyfin_api_key',
        dest='jellyfin_api_key',
        help='Jellyfin server API key',
        type=str,
        default=os.environ.get('BRAKERR_JELLYFIN_API_KEY')
    )
    argparser.add_argument(
        '--jellyfin_update_interval',
        dest='jellyfin_update_interval',
        help='Jellyfin server update interval',
        type=int,
        default=os.environ.get('BRAKERR_JELLYFIN_UPDATE_INTERVAL')
    )
    argparser.add_argument(
        '--jellyfin_ignore_paused_after',
        dest='jellyfin_ignore_paused_after',
        help='Jellyfin server update interval',
        type=int,
        default=os.environ.get('BRAKERR_JELLYFIN_IGNORE_PAUSED_AFTER')
    )
    
    argparser.add_argument(
        '--log_level',
        dest='log_level',
        help='Python logging level to stdout, use 10, 20, 30, 40, 50. Default is 20 (INFO)',
        type=int,
        default=os.environ.get('BRAKERR_LOG_LEVEL', logging.INFO)
    )
    argparser.add_argument(
        '--log_file_level',
        dest='log_file_level',
        help='Python logging level to file, use 10, 20, 30, 40, 50. Default is 30 (WARNING)',
        type=int,
        default=os.environ.get('BRAKERR_LOG_FILE_LEVEL', logging.WARNING)
    )
    return argparser.parse_args()
