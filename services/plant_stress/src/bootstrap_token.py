from db_api_client import get_or_bootstrap_token

if __name__ == "__main__":
    tok = get_or_bootstrap_token()
    print(f"[TOKEN] {tok!r}")
