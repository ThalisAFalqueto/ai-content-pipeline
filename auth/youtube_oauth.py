from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from config import YOUTUBE_OAUTH_CLIENT_SECRET_FILE, YOUTUBE_OAUTH_TOKEN_FILE

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_credentials() -> Credentials:
    creds = None
    if YOUTUBE_OAUTH_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(YOUTUBE_OAUTH_TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except RefreshError:
                # refresh token expirado/revogado (comum em apps OAuth em modo "Testing",
                # que expiram após 7 dias) — cai pro login interativo abaixo
                pass

        if not refreshed:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(YOUTUBE_OAUTH_CLIENT_SECRET_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        YOUTUBE_OAUTH_TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return creds


if __name__ == "__main__":
    get_credentials()
    print(f"Autorização concluída. Token salvo em {YOUTUBE_OAUTH_TOKEN_FILE}")
