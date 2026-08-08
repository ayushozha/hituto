import asyncio
import logging
import os
from typing import Optional

from reboot.aio.applications import Application
from reboot.aio.auth.oauth_providers import (
    Auth0,
    Development,
    GitHub,
    Google,
    OAuthProviderByEnvironment,
    Ory,
    RegisteredOAuthProvider,
)
from reboot.std.ciphertext.v1.ciphertext import ciphertext_library
from reboot.std.collections.ordered_map.v1.ordered_map import ordered_map_library

from tutor_servicer import TutorMessageServicer, TutorSessionServicer


logging.basicConfig(level=logging.INFO)


def production_oauth_provider() -> Optional[RegisteredOAuthProvider]:
    """
    Build the production sign-in provider from the environment.

    Which provider to use is a deployment decision, not a code one, so it is
    configuration. Returning None when `OAUTH_PROVIDER` is unset keeps
    Reboot's own safeguard: `rbt serve` refuses to start without a real
    provider, rather than quietly shipping the development account picker.

    Register `<APP_ORIGIN>/__/oauth/callback` as the redirect URI with
    whichever provider you choose.
    """
    name = os.environ.get("OAUTH_PROVIDER", "").strip().lower()
    if not name:
        return None

    client_id = os.environ.get("OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("OAUTH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise ValueError(
            f"OAUTH_PROVIDER={name} needs OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET."
        )

    if name == "google":
        return Google(client_id=client_id, client_secret=client_secret)
    if name == "github":
        return GitHub(client_id=client_id, client_secret=client_secret)

    # Auth0 and Ory are tenant-hosted, so they need to know which tenant.
    domain = os.environ.get("OAUTH_DOMAIN", "").strip()
    if name in {"auth0", "ory"}:
        if not domain:
            raise ValueError(f"OAUTH_PROVIDER={name} also needs OAUTH_DOMAIN.")
        if name == "auth0":
            return Auth0(domain=domain, client_id=client_id, client_secret=client_secret)
        return Ory(domain=domain, client_id=client_id, client_secret=client_secret)

    raise ValueError(
        f"Unknown OAUTH_PROVIDER {name!r}. Use google, github, auth0, or ory, "
        "or leave it unset to stay on the development account picker."
    )


async def main() -> None:
    await Application(
        servicers=[TutorSessionServicer, TutorMessageServicer],
        libraries=[ciphertext_library(), ordered_map_library()],
        oauth=OAuthProviderByEnvironment(
            dev=Development(),
            prod=production_oauth_provider(),
        ),
        allowed_origins=[os.environ.get("APP_ORIGIN", "http://localhost:5173")],
    ).run()


if __name__ == "__main__":
    asyncio.run(main())
