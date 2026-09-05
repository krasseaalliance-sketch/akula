from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, ConstructiveCabinet, ConstructiveOrganization, User
from app.security import hash_password


def test_creator_can_issue_one_time_master_invite_and_master_can_register():
    from app.constructive_api import create_master_invite, register_master_invite

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        creator = User(email="creator-cabinet@example.local", name="Алексей Мифанюк", password_hash=hash_password("secret"))
        db.add(creator)
        db.flush()
        organization = ConstructiveOrganization(name="Constructive", workspace_id="workspace-cabinet")
        db.add(organization)
        db.flush()
        db.add(ConstructiveCabinet(organization_id=organization.id, user_id=creator.id, role="CREATOR"))
        db.commit()

        issued = create_master_invite(db, creator, organization.id, "Сергей Мифанюк", "sergey-cabinet@example.local", base_url="https://example.test")
        assert issued.url.startswith("https://example.test/constructive/register/")
        assert issued.asmet_message_id

        registered = register_master_invite(db, issued.token, "Сергей Мифанюк", "master-password")
        assert registered.role == "MASTER"
        assert registered.email == "sergey-cabinet@example.local"
        with pytest.raises(ValueError, match="INVITE_ALREADY_USED"):
            register_master_invite(db, issued.token, "Сергей Мифанюк", "master-password")

