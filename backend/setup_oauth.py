"""
YouTube OAuth Setup
Run this once on VPS to get the token
"""
import os
import json

CLIENT_ID = "682704644251-h27c3e55oidg73cfqq6b318o4hgdqnet.apps.googleusercontent.com"
CLIENT_SECRET = "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"

client_secrets = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token"
    }
}

os.makedirs('credentials', exist_ok=True)
with open('credentials/client_secrets.json', 'w') as f:
    json.dump(client_secrets, f)
print("client_secrets.json created!")

# Generate auth URL
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube',
    'https://www.googleapis.com/auth/youtube.readonly'
]

flow = InstalledAppFlow.from_client_secrets_file(
    'credentials/client_secrets.json',
    scopes=SCOPES,
    redirect_uri='urn:ietf:wg:oauth:2.0:oob'
)

auth_url, _ = flow.authorization_url(prompt='consent')

print("\n" + "="*60)
print("এই URL টা browser এ খোলো:")
print("="*60)
print(auth_url)
print("="*60)
print("\nLogin করো → Allow দাও → Code copy করো")
print("তারপর এখানে paste করো:")

code = input("\nCode: ").strip()

flow.fetch_token(code=code)
creds = flow.credentials

token_data = {
    "token": creds.token,
    "refresh_token": creds.refresh_token,
    "token_uri": creds.token_uri,
    "client_id": creds.client_id,
    "client_secret": creds.client_secret,
    "scopes": list(creds.scopes)
}

with open('credentials/youtube_token.json', 'w') as f:
    json.dump(token_data, f)

print("\n✅ youtube_token.json saved!")
print("এখন app restart করো — auto upload কাজ করবে!")
