import uuid
from datetime import datetime, timezone
from enum import Enum
import re

from pydantic import EmailStr, field_validator
from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


UG_PHONE_RE = re.compile(r"^\+256[0-9]{9}$")

def get_datetime_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── Check-in ──────────────────────────────────────────────

class CheckIn(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE")
    checked_in_at: datetime = Field(default_factory=get_datetime_utc)
    checked_out_at: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None


class CheckInPublic(SQLModel):
    id: uuid.UUID
    user_id: uuid.UUID
    checked_in_at: datetime
    checked_out_at: datetime | None
    latitude: float | None
    longitude: float | None


class UserRole(str, Enum):
    HQ_ADMIN = "HQ_ADMIN"
    DG = "DG"
    RISO = "RISO"
    SISO = "SISO"
    DISO = "DISO"
    GISO = "GISO"
    AGENT = "AGENT"


class UserStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


# Role hierarchy lowest → highest (used for escalation)
ROLE_HIERARCHY = [UserRole.GISO, UserRole.DISO, UserRole.SISO, UserRole.RISO, UserRole.DG]


class Region(SQLModel, table=True):
    __tablename__ = "region"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255, unique=True, index=True)
    sectors: list["Sector"] = Relationship(back_populates="region")


class Sector(SQLModel, table=True):
    __tablename__ = "sector"
    __table_args__ = (UniqueConstraint("name", "region_id", name="uq_sector_name_region"),)
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255)
    region_id: uuid.UUID = Field(foreign_key="region.id")
    region: Region | None = Relationship(back_populates="sectors")
    districts: list["District"] = Relationship(back_populates="sector")


class District(SQLModel, table=True):
    __tablename__ = "district"
    __table_args__ = (UniqueConstraint("name", "sector_id", name="uq_district_name_sector"),)
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255)
    sector_id: uuid.UUID = Field(foreign_key="sector.id")
    sector: Sector | None = Relationship(back_populates="districts")
    counties: list["County"] = Relationship(back_populates="district")


class County(SQLModel, table=True):
    __tablename__ = "county"
    __table_args__ = (UniqueConstraint("name", "district_id", name="uq_county_name_district"),)
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255)
    district_id: uuid.UUID = Field(foreign_key="district.id")
    district: District | None = Relationship(back_populates="counties")
    subcounties: list["SubCounty"] = Relationship(back_populates="county")


class SubCounty(SQLModel, table=True):
    __tablename__ = "subcounty"
    __table_args__ = (UniqueConstraint("name", "county_id", name="uq_subcounty_name_county"),)
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255)
    county_id: uuid.UUID = Field(foreign_key="county.id")
    county: County | None = Relationship(back_populates="subcounties")
    parishes: list["Parish"] = Relationship(back_populates="subcounty")


class Parish(SQLModel, table=True):
    __tablename__ = "parish"
    __table_args__ = (UniqueConstraint("name", "subcounty_id", name="uq_parish_name_subcounty"),)
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255)
    subcounty_id: uuid.UUID = Field(foreign_key="subcounty.id")
    subcounty: SubCounty | None = Relationship(back_populates="parishes")
    villages: list["Village"] = Relationship(back_populates="parish")


class Village(SQLModel, table=True):
    __tablename__ = "village"
    __table_args__ = (UniqueConstraint("name", "parish_id", name="uq_village_name_parish"),)
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255)
    parish_id: uuid.UUID = Field(foreign_key="parish.id")
    parish: Parish | None = Relationship(back_populates="villages")


# --- Public (API response) schemas ---

class RegionPublic(SQLModel):
    id: uuid.UUID
    name: str


class SectorPublic(SQLModel):
    id: uuid.UUID
    name: str
    region_id: uuid.UUID


class DistrictPublic(SQLModel):
    id: uuid.UUID
    name: str
    sector_id: uuid.UUID


class CountyPublic(SQLModel):
    id: uuid.UUID
    name: str
    district_id: uuid.UUID


class SubCountyPublic(SQLModel):
    id: uuid.UUID
    name: str
    county_id: uuid.UUID


class ParishPublic(SQLModel):
    id: uuid.UUID
    name: str
    subcounty_id: uuid.UUID


class VillagePublic(SQLModel):
    id: uuid.UUID
    name: str
    parish_id: uuid.UUID


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)
    role: UserRole = Field(default=UserRole.AGENT)
    phone_number: str = Field(unique=True, index=True, max_length=20)
    status: UserStatus = Field(default=UserStatus.ACTIVE)
    geographical_id: uuid.UUID | None = Field(default=None, foreign_key="subcounty.id", nullable=True)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=1, max_length=128)

    @field_validator("phone_number")
    @classmethod
    def phone_must_be_ugandan(cls, v: str) -> str:
        if not UG_PHONE_RE.match(v):
            raise ValueError("Phone number must be a valid Ugandan number in format +256XXXXXXXXX")
        return v


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=1, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore[assignment]
    phone_number: str | None = Field(default=None, max_length=20)  # type: ignore[assignment]
    password: str | None = Field(default=None, min_length=1, max_length=128)
    role: UserRole | None = None  # type: ignore[assignment]
    status: UserStatus | None = None  # type: ignore[assignment]

    @field_validator("phone_number", mode="before")
    @classmethod
    def phone_must_be_ugandan(cls, v: str | None) -> str | None:  # type: ignore[override]
        if v is None:
            return v
        if not UG_PHONE_RE.match(v):
            raise ValueError("Phone number must be a valid Ugandan number in format +256XXXXXXXXX")
        return v


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    items: list["Item"] = Relationship(back_populates="owner", cascade_delete=True)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None

class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# Shared properties
class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Properties to receive on item creation
class ItemCreate(ItemBase):
    pass


# Properties to receive on item update
class ItemUpdate(ItemBase):
    title: str | None = Field(default=None, min_length=1, max_length=255)  # type: ignore[assignment]


# Database model, database table inferred from class name
class Item(ItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="items")


# Properties to return via API, id is always required
class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None


class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int


# Generic message
class Message(SQLModel):
    message: str


class Category(SQLModel, table=True):
    __tablename__ = "category"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255, unique=True, index=True)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool = Field(default=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    subcategories: list["SubCategory"] = Relationship(back_populates="category")


class SubCategory(SQLModel, table=True):
    __tablename__ = "subcategory"
    __table_args__ = (UniqueConstraint("name", "category_id", name="uq_subcategory_name_category"),)
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool = Field(default=True)
    category_id: uuid.UUID = Field(foreign_key="category.id")
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    category: Category | None = Relationship(back_populates="subcategories")


class CategoryPublic(SQLModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    is_active: bool
    created_at: datetime | None = None


class SubCategoryPublic(SQLModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    is_active: bool
    category_id: uuid.UUID
    created_at: datetime | None = None


# ── Report ────────────────────────────────────────────────

class ReportStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    REVIEW = "REVIEW"
    ESCALATED = "ESCALATED"
    CLOSED = "CLOSED"


class Report(SQLModel, table=True):
    __tablename__ = "report"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(max_length=255)
    description: str = Field(max_length=2000)
    status: ReportStatus = Field(default=ReportStatus.DRAFT)
    subcategory_id: uuid.UUID = Field(foreign_key="subcategory.id")
    submitted_by: uuid.UUID = Field(foreign_key="user.id")
    assigned_to: uuid.UUID | None = Field(default=None, foreign_key="user.id", nullable=True)
    parish_id: uuid.UUID | None = Field(default=None, foreign_key="parish.id", nullable=True)
    subcounty_id: uuid.UUID | None = Field(default=None, foreign_key="subcounty.id", nullable=True, index=True)
    latitude: float | None = Field(default=None)
    longitude: float | None = Field(default=None)
    photo_url: str | None = Field(default=None, max_length=500)
    video_url: str | None = Field(default=None, max_length=500)
    voice_url: str | None = Field(default=None, max_length=500)
    document_url: str | None = Field(default=None, max_length=500)
    program_type: str | None = Field(default=None, max_length=50, index=True)
    pdm_beneficiary_id: uuid.UUID | None = Field(default=None, nullable=True)  # → pdm_beneficiaries.id
    pdm_disbursement_id: uuid.UUID | None = Field(default=None, nullable=True)  # → pdm_disbursements.id
    outcome: str | None = Field(default=None, max_length=20)  # "CONFIRMED" | "DISPUTED"
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class ReportPublic(SQLModel):
    id: uuid.UUID
    title: str
    description: str
    status: ReportStatus
    subcategory_id: uuid.UUID
    submitted_by: uuid.UUID
    assigned_to: uuid.UUID | None = None
    parish_id: uuid.UUID | None = None
    subcounty_id: uuid.UUID | None = None
    latitude: float | None = None
    longitude: float | None = None
    photo_url: str | None = None
    video_url: str | None = None
    voice_url: str | None = None
    document_url: str | None = None
    program_type: str | None = None
    pdm_beneficiary_id: uuid.UUID | None = None
    pdm_disbursement_id: uuid.UUID | None = None
    outcome: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ReportCreate(SQLModel):
    title: str = Field(max_length=255)
    description: str = Field(max_length=2000)
    subcategory_id: uuid.UUID
    parish_id: uuid.UUID | None = None
    subcounty_id: uuid.UUID | None = None
    latitude: float | None = None
    longitude: float | None = None
    photo_url: str | None = None
    video_url: str | None = None
    voice_url: str | None = None
    document_url: str | None = None
    program_type: str | None = None
    pdm_beneficiary_id: uuid.UUID | None = None
    pdm_disbursement_id: uuid.UUID | None = None


class ReportUpdate(SQLModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    status: ReportStatus | None = None
    assigned_to: uuid.UUID | None = None
    outcome: str | None = None  # "CONFIRMED" | "DISPUTED" — set when closing a PDM report


class ReportsPublic(SQLModel):
    data: list[ReportPublic]
    count: int


# ── Task ──────────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class Task(SQLModel, table=True):
    __tablename__ = "task"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    assigned_to: uuid.UUID = Field(foreign_key="user.id")
    created_by: uuid.UUID = Field(foreign_key="user.id")
    due_date: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    photo_url: str | None = Field(default=None, max_length=500)
    video_url: str | None = Field(default=None, max_length=500)
    voice_url: str | None = Field(default=None, max_length=500)
    document_url: str | None = Field(default=None, max_length=500)
    pdm_beneficiary_id: uuid.UUID | None = Field(default=None, nullable=True)
    pdm_disbursement_id: uuid.UUID | None = Field(default=None, nullable=True)
    created_at: datetime | None = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))  # type: ignore
    updated_at: datetime | None = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))  # type: ignore


class TaskPublic(SQLModel):
    id: uuid.UUID
    title: str
    description: str | None = None
    status: TaskStatus
    assigned_to: uuid.UUID
    created_by: uuid.UUID
    due_date: datetime | None = None
    photo_url: str | None = None
    video_url: str | None = None
    voice_url: str | None = None
    document_url: str | None = None
    pdm_beneficiary_id: uuid.UUID | None = None
    pdm_disbursement_id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TaskCreate(SQLModel):
    title: str = Field(max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    assigned_to: uuid.UUID
    due_date: datetime | None = None
    photo_url: str | None = None
    video_url: str | None = None
    voice_url: str | None = None
    document_url: str | None = None
    pdm_beneficiary_id: uuid.UUID | None = None
    pdm_disbursement_id: uuid.UUID | None = None


class TaskUpdate(SQLModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    status: TaskStatus | None = None
    assigned_to: uuid.UUID | None = None
    due_date: datetime | None = None


class TasksPublic(SQLModel):
    data: list[TaskPublic]
    count: int


# ── GPS Log ───────────────────────────────────────────────

class GpsLog(SQLModel, table=True):
    __tablename__ = "gps_log"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    agent_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    latitude: float
    longitude: float
    recorded_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class GpsLogPublic(SQLModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    latitude: float
    longitude: float
    recorded_at: datetime


class GpsLogCreate(SQLModel):
    latitude: float
    longitude: float


# ── Device ────────────────────────────────────────────────

class DeviceStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class Device(SQLModel, table=True):
    __tablename__ = "device"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    serial_number: str = Field(max_length=255, unique=True, index=True)
    model: str = Field(max_length=255)
    assigned_to: uuid.UUID | None = Field(default=None, foreign_key="user.id", nullable=True)
    status: DeviceStatus = Field(default=DeviceStatus.OFFLINE)
    last_seen: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class DevicePublic(SQLModel):
    id: uuid.UUID
    serial_number: str
    model: str
    assigned_to: uuid.UUID | None = None
    status: DeviceStatus
    last_seen: datetime | None = None
    created_at: datetime | None = None


class DeviceCreate(SQLModel):
    serial_number: str = Field(max_length=255)
    model: str = Field(max_length=255)
    assigned_to: uuid.UUID | None = None


class DeviceUpdate(SQLModel):
    assigned_to: uuid.UUID | None = None
    status: DeviceStatus | None = None


class DevicesPublic(SQLModel):
    data: list[DevicePublic]
    count: int


# ── Push Tokens ───────────────────────────────────────────

class PushToken(SQLModel, table=True):
    __tablename__ = "push_token"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    token: str = Field(max_length=255, unique=True, index=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


# ── PDM (Parish Development Model) ───────────────────────

class BeneficiaryStatus(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FLAGGED = "FLAGGED"


class DisbursementStatus(str, Enum):
    PENDING = "PENDING"
    DISBURSED = "DISBURSED"
    FAILED = "FAILED"


class Beneficiary(SQLModel, table=True):
    __tablename__ = "beneficiary"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    full_name: str = Field(max_length=255)
    national_id: str = Field(max_length=100, unique=True, index=True)
    phone_number: str | None = Field(default=None, max_length=50)
    parish_id: uuid.UUID | None = Field(default=None, foreign_key="parish.id", nullable=True)
    notes: str | None = Field(default=None, max_length=1000)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    disbursements: list["Disbursement"] = Relationship(back_populates="beneficiary")


class Disbursement(SQLModel, table=True):
    __tablename__ = "disbursement"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    beneficiary_id: uuid.UUID = Field(foreign_key="beneficiary.id")
    amount: float
    currency: str = Field(default="UGX", max_length=10)
    status: DisbursementStatus = Field(default=DisbursementStatus.PENDING)
    disbursed_by: uuid.UUID | None = Field(default=None, foreign_key="user.id", nullable=True)
    disbursed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    notes: str | None = Field(default=None, max_length=1000)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    beneficiary: Beneficiary | None = Relationship(back_populates="disbursements")


class BeneficiaryPublic(SQLModel):
    id: uuid.UUID
    full_name: str
    national_id: str
    phone_number: str | None = None
    parish_id: uuid.UUID | None = None
    notes: str | None = None
    created_at: datetime | None = None


class BeneficiaryCreate(SQLModel):
    full_name: str = Field(max_length=255)
    national_id: str = Field(max_length=100)
    phone_number: str | None = None
    parish_id: uuid.UUID | None = None
    notes: str | None = None


class BeneficiaryUpdate(SQLModel):
    full_name: str | None = None
    phone_number: str | None = None
    parish_id: uuid.UUID | None = None
    notes: str | None = None


class BeneficiariesPublic(SQLModel):
    data: list[BeneficiaryPublic]
    count: int


class DisbursementPublic(SQLModel):
    id: uuid.UUID
    beneficiary_id: uuid.UUID
    amount: float
    currency: str
    status: DisbursementStatus
    disbursed_by: uuid.UUID | None = None
    disbursed_at: datetime | None = None
    notes: str | None = None
    created_at: datetime | None = None


class DisbursementCreate(SQLModel):
    beneficiary_id: uuid.UUID
    amount: float
    currency: str = "UGX"
    notes: str | None = None


class DisbursementUpdate(SQLModel):
    status: DisbursementStatus | None = None
    notes: str | None = None


class DisbursementsPublic(SQLModel):
    data: list[DisbursementPublic]
    count: int


# ── Audit Log ─────────────────────────────────────────────

class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    actor_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    action: str = Field(max_length=100)          # e.g. "report.status_changed"
    entity_type: str = Field(max_length=100)     # e.g. "report"
    entity_id: uuid.UUID
    detail: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class AuditLogPublic(SQLModel):
    id: uuid.UUID
    actor_id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    detail: str | None = None
    created_at: datetime


class AuditLogsPublic(SQLModel):
    data: list[AuditLogPublic]
    count: int


# ── Device Commands ───────────────────────────────────────

class DeviceCommandType(str, Enum):
    LOGOUT = "LOGOUT"
    DISABLE = "DISABLE"
    ENABLE = "ENABLE"
    WIPE = "WIPE"


class DeviceCommandStatus(str, Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"


class DeviceCommandRecord(SQLModel, table=True):
    __tablename__ = "device_command"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    issued_by: uuid.UUID = Field(foreign_key="user.id")
    command: DeviceCommandType
    status: DeviceCommandStatus = Field(default=DeviceCommandStatus.PENDING)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class DeviceCommandPublic(SQLModel):
    id: uuid.UUID
    user_id: uuid.UUID
    issued_by: uuid.UUID
    command: DeviceCommandType
    status: DeviceCommandStatus
    created_at: datetime


# ── Notifications ─────────────────────────────────────────

class NotificationType(str, Enum):
    TASK = "TASK"
    REPORT = "REPORT"
    ALERT = "ALERT"
    INFO = "INFO"


class Notification(SQLModel, table=True):
    __tablename__ = "notification"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    type: NotificationType
    title: str = Field(max_length=255)
    message: str = Field(max_length=1000)
    read: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class NotificationPublic(SQLModel):
    id: uuid.UUID
    user_id: uuid.UUID
    type: NotificationType
    title: str
    message: str
    read: bool
    created_at: datetime


# ── OTP Record ────────────────────────────────────────────

class OtpRecord(SQLModel, table=True):
    __tablename__ = "otp_record"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    phone_number: str = Field(max_length=20, index=True)
    otp_hash: str = Field(max_length=255)
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
    used: bool = Field(default=False)
    created_at: datetime = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))


# ── Device PIN ────────────────────────────────────────────

class DevicePin(SQLModel, table=True):
    __tablename__ = "device_pin"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    device_id: str = Field(max_length=255, index=True)
    pin_hash: str = Field(max_length=255)
    created_at: datetime = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole | None = None


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None
    role: UserRole | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=1, max_length=128)


# ── Alert ─────────────────────────────────────────────────

class AlertCategory(str, Enum):
    HOTSPOT = "HOTSPOT"
    INCIDENT = "INCIDENT"
    COMMUNITY_TENSION = "COMMUNITY_TENSION"
    POLICE_OPERATION = "POLICE_OPERATION"


class Alert(SQLModel, table=True):
    __tablename__ = "alert"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    category: AlertCategory = Field(index=True)
    title: str = Field(max_length=255)
    description: str = Field(max_length=1000)
    subcounty_id: uuid.UUID | None = Field(default=None, foreign_key="subcounty.id", nullable=True, index=True)
    parish_id: uuid.UUID | None = Field(default=None, foreign_key="parish.id", nullable=True)
    latitude: float | None = None
    longitude: float | None = None
    source_report_id: uuid.UUID | None = Field(default=None, foreign_key="report.id", nullable=True)
    source_task_id: uuid.UUID | None = Field(default=None, foreign_key="task.id", nullable=True)
    severity_score: float = Field(default=0.0)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True), index=True)
    updated_at: datetime = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))


class AlertPublic(SQLModel):
    id: uuid.UUID
    category: AlertCategory
    title: str
    description: str
    subcounty_id: uuid.UUID | None = None
    parish_id: uuid.UUID | None = None
    latitude: float | None = None
    longitude: float | None = None
    source_report_id: uuid.UUID | None = None
    source_task_id: uuid.UUID | None = None
    severity_score: float
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AlertsPublic(SQLModel):
    data: list[AlertPublic]
    count: int
