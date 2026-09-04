"""Interactive one-time local owner bootstrap. There is no HTTP equivalent."""

import argparse
import getpass
from uuid import uuid4

from mask_api.modules.identity.auth_contracts import BootstrapOwnerRequest
from mask_api.modules.identity.errors import (
    BootstrapAlreadyCompleted,
    IdentityUnavailable,
    PasswordPolicyViolation,
)
from mask_api.modules.identity.wiring import get_owner_bootstrap_service


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Create the first local MASK owner account")
    command.add_argument("--organization", required=True, help="Local organization name")
    command.add_argument("--name", required=True, help="Owner display name")
    command.add_argument("--email", required=True, help="Owner login email")
    return command


def main(arguments: list[str] | None = None) -> int:
    options = parser().parse_args(arguments)
    password = getpass.getpass("New owner password: ")
    confirmation = getpass.getpass("Confirm owner password: ")
    if password != confirmation:
        print("Owner bootstrap denied: password confirmation did not match.")
        return 2
    try:
        request = BootstrapOwnerRequest(
            organization_name=options.organization,
            owner_name=options.name,
            email=options.email,
            password=password,
            correlation_id=uuid4(),
        )
        result = get_owner_bootstrap_service().create_owner(request)
    except (PasswordPolicyViolation, ValueError):
        print("Owner bootstrap denied: check the supplied names, email, and password policy.")
        return 2
    except BootstrapAlreadyCompleted:
        print("Owner bootstrap denied: an organization already exists.")
        return 2
    except IdentityUnavailable:
        print("Owner bootstrap failed safely: identity storage is unavailable.")
        return 1
    print(
        "Owner bootstrap complete. Organization ID: "
        f"{result.organization_id}; User ID: {result.user_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
