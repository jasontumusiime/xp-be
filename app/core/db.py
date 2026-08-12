from sqlmodel import Session, create_engine, select

from app import crud
from app.core.config import settings
from app.models import User, UserCreate, UserRole

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))


# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28


def init_db(session: Session) -> None:
    # Tables should be created with Alembic migrations
    # But if you don't want to use migrations, create
    # the tables un-commenting the next lines
    # from sqlmodel import SQLModel

    # This works because the models are already imported and registered from app.models.
    # For local SQLite fallback, auto-create tables when migrations are not available.
    from sqlmodel import SQLModel
    if engine.url.get_backend_name() == "sqlite":
        SQLModel.metadata.create_all(engine)

    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            phone_number=settings.FIRST_SUPERUSER_PHONE,
            is_superuser=True,
            role=UserRole.HQ_ADMIN,
        )
        user = crud.create_user(session=session, user_create=user_in)
    elif not user.phone_number:
        # Backfill phone for existing superuser created before phone was required
        user.phone_number = settings.FIRST_SUPERUSER_PHONE
        session.add(user)
        session.commit()
