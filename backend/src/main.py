import asyncio
import logging
import os

from reboot.aio.applications import Application
from reboot.aio.auth.oauth_providers import Development, OAuthProviderByEnvironment
from reboot.std.ciphertext.v1.ciphertext import ciphertext_library
from reboot.std.collections.ordered_map.v1.ordered_map import ordered_map_library

from tutor_servicer import TutorMessageServicer, TutorSessionServicer


logging.basicConfig(level=logging.INFO)


async def main() -> None:
    await Application(
        servicers=[TutorSessionServicer, TutorMessageServicer],
        libraries=[ciphertext_library(), ordered_map_library()],
        oauth=OAuthProviderByEnvironment(dev=Development(), prod=None),
        allowed_origins=[os.environ.get("APP_ORIGIN", "http://localhost:5173")],
    ).run()


if __name__ == "__main__":
    asyncio.run(main())
