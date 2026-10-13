"""Build token.pickle from the OAuth token of a Google Drive remote in rclone.conf.

Lets the bot's own Drive features (clone, count, list, gd uploads) reuse the same
sign-in as rclone. Usage: python3 token_from_rclone.py [remote]  (default: gdrive)
"""

import json
import pickle
import sys
from configparser import RawConfigParser

from google.oauth2.credentials import Credentials

remote = sys.argv[1] if len(sys.argv) > 1 else "gdrive"
config = RawConfigParser()
config.read("rclone.conf")
if not config.has_section(remote) or config.get(remote, "type", fallback="") != "drive":
    sys.exit(f"token_from_rclone: no drive remote [{remote}] in rclone.conf")

token = json.loads(config.get(remote, "token"))
credentials = Credentials(
    token=None,
    refresh_token=token["refresh_token"],
    token_uri="https://oauth2.googleapis.com/token",
    client_id=config.get(remote, "client_id"),
    client_secret=config.get(remote, "client_secret"),
    scopes=["https://www.googleapis.com/auth/drive"],
)
with open("token.pickle", "wb") as f:
    pickle.dump(credentials, f)
print(f"token_from_rclone: token.pickle created from [{remote}]")
