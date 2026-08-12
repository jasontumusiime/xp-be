"""
Seed script — generates ~50,000 realistic records for the Xpurse platform.
Run from /backend:  ../.venv/bin/python seed.py
"""
import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select, func
from app.core.db import engine
from app.core.security import get_password_hash
from app.models import (
    Region, Sector, District, County, SubCounty, Parish,
    User, UserRole, UserStatus,
    Category, SubCategory,
    Report, ReportStatus,
    Task, TaskStatus,
    GpsLog,
    Device, DeviceStatus,
    Beneficiary, BeneficiaryStatus,
    Disbursement, DisbursementStatus,
    AuditLog,
)

rng = random.Random(42)

def utc(days_ago=0, hours_ago=0):
    return datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)

# ── Uganda geography ──────────────────────────────────────
REGIONS = ["Central", "Eastern", "Northern", "Western", "Kampala Metropolitan"]
SECTORS_PER_REGION = [
    ["Buganda", "Busoga", "Bunyoro"],
    ["Bukedi", "Bugisu", "Teso", "Karamoja"],
    ["Acholi", "Lango", "West Nile"],
    ["Ankole", "Kigezi", "Tooro"],
    ["Kampala", "Wakiso"],
]
DISTRICTS = {
    "Buganda": ["Masaka", "Mubende", "Mityana", "Kiboga"],
    "Busoga": ["Jinja", "Iganga", "Kamuli", "Bugiri"],
    "Bunyoro": ["Hoima", "Masindi", "Kibaale"],
    "Bukedi": ["Tororo", "Busia", "Pallisa"],
    "Bugisu": ["Mbale", "Sironko", "Manafwa"],
    "Teso": ["Soroti", "Kumi", "Kaberamaido"],
    "Karamoja": ["Moroto", "Kotido", "Abim"],
    "Acholi": ["Gulu", "Kitgum", "Pader"],
    "Lango": ["Lira", "Apac", "Oyam"],
    "West Nile": ["Arua", "Nebbi", "Zombo"],
    "Ankole": ["Mbarara", "Bushenyi", "Ntungamo"],
    "Kigezi": ["Kabale", "Kisoro", "Rukungiri"],
    "Tooro": ["Fort Portal", "Kyenjojo", "Kamwenge"],
    "Kampala": ["Kampala Central", "Kawempe", "Makindye", "Nakawa", "Rubaga"],
    "Wakiso": ["Entebbe", "Nansana", "Kira", "Makindye Ssabagabo"],
}
PARISHES_PER_DISTRICT = ["North", "South", "East", "West", "Central"]

FIRST_NAMES = ["John", "Sarah", "Peter", "James", "Naomi", "Grace", "David", "Mary",
               "Robert", "Agnes", "Paul", "Ruth", "Moses", "Esther", "Isaac", "Lydia",
               "Samuel", "Deborah", "Joseph", "Miriam", "Daniel", "Priscilla", "Michael",
               "Judith", "Emmanuel", "Charity", "Francis", "Patience", "George", "Faith"]
LAST_NAMES = ["Okello", "Nakato", "Ssemakula", "Atim", "Mugisha", "Opio", "Namukasa",
              "Tumwine", "Auma", "Byaruhanga", "Nanteza", "Kiggundu", "Odongo", "Namutebi",
              "Wasswa", "Akello", "Lubega", "Nankya", "Ssali", "Kyomuhendo"]

CATEGORIES_DATA = {
    "Security Incident": ["Armed Robbery", "Assault", "Kidnapping", "Shooting", "Mob Justice"],
    "Suspicious Activity": ["Unusual Movement", "Surveillance", "Unknown Vehicles", "Night Activity"],
    "Civil Disturbance": ["Protest", "Riot", "Land Dispute", "Community Conflict"],
    "Theft / Robbery": ["Livestock Theft", "Burglary", "Pickpocketing", "Vehicle Theft"],
    "Other": ["Fire Outbreak", "Accident", "Missing Person", "Environmental Hazard"],
}

DEVICE_MODELS = ["Zebra TC27", "Zebra TC52", "Zebra TC57", "Zebra TC72"]

REPORT_TITLES = [
    "Suspicious vehicle spotted near market",
    "Armed men seen at district border",
    "Protest gathering at town centre",
    "Livestock theft reported by farmer",
    "Unknown individuals conducting surveillance",
    "Night movement of armed group",
    "Land dispute escalating between communities",
    "Fire outbreak at trading centre",
    "Missing person reported by family",
    "Robbery at mobile money agent",
    "Assault incident near school",
    "Illegal roadblock set up on highway",
    "Kidnapping attempt foiled by locals",
    "Shooting incident at bar",
    "Community conflict over water source",
]

BENEFICIARY_NAMES = [
    ("Apio Grace", "CF"), ("Okello James", "CM"), ("Nakato Sarah", "CF"),
    ("Mugisha Robert", "CM"), ("Atim Agnes", "CF"), ("Opio David", "CM"),
    ("Namukasa Mary", "CF"), ("Tumwine Paul", "CM"), ("Auma Ruth", "CF"),
    ("Byaruhanga Moses", "CM"), ("Nanteza Esther", "CF"), ("Kiggundu Isaac", "CM"),
    ("Odongo Lydia", "CF"), ("Namutebi Samuel", "CM"), ("Wasswa Deborah", "CF"),
]

def phone(i: int) -> str:
    return f"+2567{str(i).zfill(8)}"

def bulk_insert(session, objects, batch=500):
    for i in range(0, len(objects), batch):
        session.add_all(objects[i:i+batch])
        session.flush()
    session.commit()

print("Seeding database…")

with Session(engine) as session:
    # ── Geography ─────────────────────────────────────────
    print("  Geography…")
    regions, sectors, districts, parishes = [], [], [], []
    all_parishes = []

    for ri, rname in enumerate(REGIONS):
        if not session.exec(select(Region).where(Region.name == rname)).first():
            r = Region(name=rname)
            session.add(r)
    session.flush()

    for ri, rname in enumerate(REGIONS):
        r = session.exec(select(Region).where(Region.name == rname)).one()
        for sname in SECTORS_PER_REGION[ri]:
            if not session.exec(select(Sector).where(Sector.name == sname, Sector.region_id == r.id)).first():
                s = Sector(name=sname, region_id=r.id)
                session.add(s)
    session.flush()

    for s in session.exec(select(Sector)).all():
        for dname in DISTRICTS.get(s.name, [f"{s.name} District"]):
            if not session.exec(select(District).where(District.name == dname, District.sector_id == s.id)).first():
                d = District(name=dname, sector_id=s.id)
                session.add(d)
    session.flush()

    for d in session.exec(select(District)).all():
        # Each mock district gets one county and one subcounty (for dev/test)
        county = session.exec(select(County).where(County.name == d.name, County.district_id == d.id)).first()
        if not county:
            county = County(name=d.name, district_id=d.id)
            session.add(county)
            session.flush()
        subcounty = session.exec(select(SubCounty).where(SubCounty.name == d.name, SubCounty.county_id == county.id)).first()
        if not subcounty:
            subcounty = SubCounty(name=d.name, county_id=county.id)
            session.add(subcounty)
            session.flush()
        for pname in PARISHES_PER_DISTRICT:
            full = f"{pname} {d.name}"
            if not session.exec(select(Parish).where(Parish.name == full, Parish.subcounty_id == subcounty.id)).first():
                p = Parish(name=full, subcounty_id=subcounty.id)
                session.add(p)
    session.flush()
    session.commit()

    all_parishes = session.exec(select(Parish)).all()
    parish_ids = [p.id for p in all_parishes]
    print(f"    {len(parish_ids)} parishes created")

    # ── Categories ────────────────────────────────────────
    print("  Categories…")
    cat_objs, subcat_objs = [], []
    for cname, subs in CATEGORIES_DATA.items():
        if not session.exec(select(Category).where(Category.name == cname)).first():
            c = Category(name=cname)
            session.add(c)
    session.flush()

    for cname, subs in CATEGORIES_DATA.items():
        c = session.exec(select(Category).where(Category.name == cname)).one()
        for sname in subs:
            if not session.exec(select(SubCategory).where(SubCategory.name == sname, SubCategory.category_id == c.id)).first():
                sc = SubCategory(name=sname, category_id=c.id)
                session.add(sc)
    session.flush()
    session.commit()

    subcat_ids = [sc.id for sc in session.exec(select(SubCategory)).all()]
    print(f"    {len(subcat_ids)} subcategories created")

    # ── Users ─────────────────────────────────────────────
    print("  Users (500)…")
    # Get existing superuser
    superuser = session.exec(select(User).where(User.is_superuser == True)).first()
    superuser_id = superuser.id if superuser else None

    existing_user_count = session.exec(select(func.count()).select_from(User)).one()
    hashed_pw = get_password_hash("xpurse2026")
    roles_dist = [UserRole.DG]*2 + [UserRole.RISO]*5 + [UserRole.SISO]*10 + \
                 [UserRole.DISO]*20 + [UserRole.GISO]*50 + [UserRole.AGENT]*413

    users = []
    phone_counter = 700100000 + existing_user_count
    for i, role in enumerate(roles_dist):
        fn = rng.choice(FIRST_NAMES)
        ln = rng.choice(LAST_NAMES)
        u = User(
            email=f"user{existing_user_count+i+1}@xpurse.net",
            full_name=f"{fn} {ln}",
            hashed_password=hashed_pw,
            role=role,
            phone_number=phone(phone_counter + i),
            status=UserStatus.ACTIVE if rng.random() > 0.05 else UserStatus.INACTIVE,
            geographical_id=rng.choice(parish_ids),
            is_active=True,
            is_superuser=False,
        )
        users.append(u)

    bulk_insert(session, users)
    all_users = session.exec(select(User)).all()
    agent_ids = [u.id for u in all_users if u.role == UserRole.AGENT]
    admin_ids = [u.id for u in all_users if u.role != UserRole.AGENT and not u.is_superuser]
    all_user_ids = [u.id for u in all_users]
    print(f"    {len(all_users)} total users ({len(agent_ids)} agents)")

    # ── Devices ───────────────────────────────────────────
    print("  Devices (500)…")
    devices = []
    for i, agent_id in enumerate(agent_ids[:500]):
        d = Device(
            serial_number=f"ZTC27-{str(i+1).zfill(4)}",
            model=rng.choice(DEVICE_MODELS),
            assigned_to=agent_id,
            status=DeviceStatus.ONLINE if rng.random() > 0.15 else DeviceStatus.OFFLINE,
            last_seen=utc(days_ago=rng.randint(0, 3), hours_ago=rng.randint(0, 23)),
        )
        devices.append(d)
    bulk_insert(session, devices)
    print(f"    {len(devices)} devices created")

    # ── Reports ───────────────────────────────────────────
    print("  Reports (20,000)…")
    statuses = list(ReportStatus)
    reports = []
    for i in range(20000):
        days = rng.randint(0, 180)
        reports.append(Report(
            title=rng.choice(REPORT_TITLES),
            description=f"Incident reported in {rng.choice(all_parishes).name}. Details: {rng.choice(REPORT_TITLES).lower()}.",
            status=rng.choice(statuses),
            subcategory_id=rng.choice(subcat_ids),
            submitted_by=rng.choice(agent_ids),
            parish_id=rng.choice(parish_ids),
            latitude=rng.uniform(0.5, 4.2),
            longitude=rng.uniform(29.5, 35.0),
            created_at=utc(days_ago=days),
            updated_at=utc(days_ago=max(0, days - rng.randint(0, 5))),
        ))
    bulk_insert(session, reports)
    report_ids = [r for r in session.exec(select(Report.id)).all()]
    print(f"    {len(report_ids)} reports created")

    # ── Tasks ─────────────────────────────────────────────
    print("  Tasks (5,000)…")
    task_statuses = list(TaskStatus)
    tasks = []
    for i in range(5000):
        days = rng.randint(0, 90)
        tasks.append(Task(
            title=f"Investigate: {rng.choice(REPORT_TITLES).lower()}",
            description=f"Follow up on incident in {rng.choice(all_parishes).name}.",
            status=rng.choice(task_statuses),
            assigned_to=rng.choice(agent_ids),
            created_by=rng.choice(admin_ids),
            due_date=utc(days_ago=-rng.randint(1, 14)),
            created_at=utc(days_ago=days),
            updated_at=utc(days_ago=max(0, days - rng.randint(0, 3))),
        ))
    bulk_insert(session, tasks)
    print(f"    {len(tasks)} tasks created")

    # ── GPS Logs ──────────────────────────────────────────
    print("  GPS Logs (20,000)…")
    gps_logs = []
    for _ in range(20000):
        agent_id = rng.choice(agent_ids)
        gps_logs.append(GpsLog(
            agent_id=agent_id,
            latitude=rng.uniform(0.5, 4.2),
            longitude=rng.uniform(29.5, 35.0),
            recorded_at=utc(days_ago=rng.randint(0, 30), hours_ago=rng.randint(0, 23)),
        ))
    bulk_insert(session, gps_logs)
    print(f"    {len(gps_logs)} GPS logs created")

    # ── Beneficiaries ─────────────────────────────────────
    print("  Beneficiaries (3,000)…")
    ben_statuses = list(BeneficiaryStatus)
    beneficiaries = []
    for i in range(3000):
        name_pair = rng.choice(BENEFICIARY_NAMES)
        beneficiaries.append(Beneficiary(
            full_name=f"{name_pair[0]} {rng.choice(LAST_NAMES)}",
            national_id=f"CM{str(rng.randint(10000000, 99999999))}{'M' if name_pair[1]=='CM' else 'F'}",
            phone_number=phone(800000000 + i),
            parish_id=rng.choice(parish_ids),
            status=rng.choices(ben_statuses, weights=[20, 60, 20])[0],
            notes="Registered beneficiary" if rng.random() > 0.7 else None,
            created_at=utc(days_ago=rng.randint(0, 365)),
        ))
    bulk_insert(session, beneficiaries)
    ben_ids = [b for b in session.exec(select(Beneficiary.id)).all()]
    print(f"    {len(ben_ids)} beneficiaries created")

    # ── Disbursements ─────────────────────────────────────
    print("  Disbursements (5,000)…")
    disb_statuses = list(DisbursementStatus)
    disbursements = []
    for _ in range(5000):
        status = rng.choices(disb_statuses, weights=[15, 75, 10])[0]
        disbursements.append(Disbursement(
            beneficiary_id=rng.choice(ben_ids),
            amount=rng.choice([50000, 100000, 150000, 200000, 250000, 500000]),
            currency="UGX",
            status=status,
            disbursed_by=rng.choice(admin_ids) if status == DisbursementStatus.DISBURSED else None,
            disbursed_at=utc(days_ago=rng.randint(0, 90)) if status == DisbursementStatus.DISBURSED else None,
            created_at=utc(days_ago=rng.randint(0, 180)),
        ))
    bulk_insert(session, disbursements)
    print(f"    {len(disbursements)} disbursements created")

    # ── Audit Logs ────────────────────────────────────────
    print("  Audit Logs (2,000)…")
    actions = [
        ("report.status_changed", "report"),
        ("task.status_changed", "task"),
        ("agent.panic", "user"),
    ]
    audit_logs = []
    for _ in range(2000):
        action, entity_type = rng.choice(actions)
        entity_id = rng.choice(report_ids) if entity_type == "report" else rng.choice(all_user_ids)
        audit_logs.append(AuditLog(
            actor_id=rng.choice(all_user_ids),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=f"status → {rng.choice(['SUBMITTED','REVIEW','ESCALATED','CLOSED'])}",
            created_at=utc(days_ago=rng.randint(0, 90)),
        ))
    bulk_insert(session, audit_logs)
    print(f"    {len(audit_logs)} audit logs created")

print("\nDone! Summary:")
with Session(engine) as session:
    for model, label in [
        (Region, "Regions"), (Sector, "Sectors"), (District, "Districts"), (Parish, "Parishes"),
        (User, "Users"), (Category, "Categories"), (SubCategory, "SubCategories"),
        (Report, "Reports"), (Task, "Tasks"), (GpsLog, "GPS Logs"),
        (Device, "Devices"), (Beneficiary, "Beneficiaries"),
        (Disbursement, "Disbursements"), (AuditLog, "Audit Logs"),
    ]:
        count = session.exec(select(func.count()).select_from(model)).one()
        print(f"  {label}: {count:,}")
