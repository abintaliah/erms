"""Install built-in configurations through the ordinary governed service.

Run as a deployment operation with --administrator-id and --operational-owner.
Existing active configurations are preserved; no administrator text is replaced.
"""

import argparse
import json
from pathlib import Path


def configure(c, administrator_id, operational_owner):
    from backend.services.api.hold_notifications import definitions
    from backend.services.api.messaging import notification_configuration as config
    from backend.services.api.audit_context import event_source_context

    config.require_admin(c, administrator_id)
    templates = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "database/seeds/hold-notification-templates.json"
        ).read_text()
    )
    source = event_source_context.set("seeding")
    installed = []
    try:
        for definition in definitions():
            _, producer = config.verify_contract(c, definition.producer_code)
            if producer["active_configuration_version_id"]:
                continue
            state = config.state(c, definition.producer_code)
            # Preserve pending administrator drafts too: never silently supersede them.
            if state["latest_version"]:
                continue
            payload = config.Configuration(
                expected_version=0,
                enabled=True,
                audience_mode=next(iter(definition.audience_resolvers)),
                operational_owner=operational_owner,
                templates=[
                    config.Template(
                        language_tag=tag,
                        subject_template=text[0],
                        body_template_rich_text=text[1],
                        review_status="published",
                    )
                    for tag, text in templates[definition.producer_code].items()
                ],
            )
            reason = "Install approved built-in legal-hold notification templates"
            version = config.save(
                c, administrator_id, definition.producer_code, payload, reason
            )
            config.activate(
                c,
                administrator_id,
                definition.producer_code,
                version["id"],
                config.Expected(expected_version=version["version"]),
                reason,
            )
            installed.append(definition.producer_code)
    finally:
        event_source_context.reset(source)
    return installed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--administrator-id", type=int, required=True)
    parser.add_argument("--operational-owner", required=True)
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    from backend.services.api.database import open_pool, close_pool
    from backend.services.api.messaging.notification_registry import initialize_registry
    from backend.services.api.messaging.transactions import run

    initialize_registry()
    open_pool()
    try:
        installed = run(
            args.administrator_id,
            lambda c: configure(c, args.administrator_id, args.operational_owner),
        )
        print(
            "Configured: "
            + (", ".join(installed) or "none; existing configurations preserved")
        )
    finally:
        close_pool()


if __name__ == "__main__":
    main()
