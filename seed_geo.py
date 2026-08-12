"""
Geo seed script — populates Region → Sector → District → County
                  → SubCounty → Parish → Village using ug-locale npm package data.

Run from /backend:  ../.venv/bin/python seed_geo.py

Requires ug-locale installed globally:  npm install -g ug-locale
"""
import json
import os
import subprocess
import tempfile
import uuid

from sqlmodel import Session, select

from app.core.db import engine
from app.models import County, District, Parish, Region, Sector, SubCounty, Village

# ── Region → Sector (SubRegion) → District mapping ───────────────────────────
# Uganda's official administrative regions and their sub-regions (sectors).
# Districts are matched by name against ug-locale data (case-insensitive).
REGION_SECTOR_DISTRICT: dict[str, dict[str, list[str]]] = {
    "Central": {
        "Buganda North": [
            "KAMPALA", "WAKISO", "MUKONO", "KAYUNGA", "BUIKWE", "BUVUMA",
            "LUWEERO", "NAKASEKE", "NAKASONGOLA", "KIBOGA", "KYANKWANZI",
            "KASANDA", "MUBENDE", "MITYANA",
        ],
        "Buganda South": [
            "MASAKA", "KALUNGU", "BUKOMANSIMBI", "LWENGO", "LYANTONDE",
            "RAKAI", "KYOTERA", "SSEMBABULE", "GOMBA", "BUTAMBALA", "MPIGI",
            "KALANGALA",
        ],
    },
    "Eastern": {
        "Busoga": [
            "JINJA", "IGANGA", "KAMULI", "BUGIRI", "MAYUGE", "NAMAYINGO",
            "LUUKA", "BUYENDE", "KALIRO", "NAMUTUMBA", "BUGWERI",
        ],
        "Bukedi": [
            "TORORO", "BUSIA", "PALLISA", "BUDAKA", "BUTALEJA", "KIBUKU",
            "BUTEBO",
        ],
        "Bugisu": [
            "MBALE", "SIRONKO", "MANAFWA", "BUDUDA", "NAMISINDWA", "BULAMBULI",
        ],
        "Sebei": [
            "KAPCHORWA", "KWEEN", "BUKWO",
        ],
        "Teso": [
            "SOROTI", "KUMI", "KABERAMAIDO", "AMURIA", "BUKEDEA", "NGORA",
            "SERERE", "KATAKWI", "KAPELEBYONG", "KALAKI",
        ],
        "Karamoja": [
            "MOROTO", "KOTIDO", "ABIM", "KAABONG", "NAKAPIRIPIRIT", "AMUDAT",
            "NAPAK", "NABILATUK", "KARENGA",
        ],
    },
    "Northern": {
        "Acholi": [
            "GULU", "KITGUM", "PADER", "AMURU", "NWOYA", "AGAGO", "OMORO",
            "LAMWO",
        ],
        "Lango": [
            "LIRA", "APAC", "OYAM", "AMOLATAR", "DOKOLO", "KOLE", "ALEBTONG",
            "OTUKE", "KWANIA",
        ],
        "West Nile": [
            "ARUA", "NEBBI", "ADJUMANI", "MOYO", "YUMBE", "KOBOKO", "MARACHA",
            "ZOMBO", "PAKWACH", "MADI-OKOLLO", "OBONGI",
        ],
    },
    "Western": {
        "Bunyoro": [
            "HOIMA", "MASINDI", "KIBAALE", "BULIISA", "KIRYANDONGO", "KAGADI",
            "KAKUMIRO", "KIKUUBE",
        ],
        "Tooro": [
            "KABAROLE", "KYENJOJO", "KAMWENGE", "KYEGEGWA", "NTOROKO",
            "KITAGWENDA", "BUNYANGABU", "BUNDIBUGYO", "KASESE",
        ],
        "Ankole": [
            "MBARARA", "BUSHENYI", "NTUNGAMO", "ISINGIRO", "KIRUHURA",
            "IBANDA", "MITOOMA", "SHEEMA", "BUHWEJU", "RUBIRIZI", "RWAMPARA",
            "KAZO",
        ],
        "Kigezi": [
            "KABALE", "KISORO", "RUKUNGIRI", "KANUNGU", "RUBANDA", "RUKIGA",
        ],
    },
}


def get_ug_locale_data() -> dict:
    """Dump all ug-locale data to JSON via a temporary Node.js script."""
    npm_root = subprocess.run(
        ["npm", "root", "-g"], capture_output=True, text=True, check=True
    ).stdout.strip()

    js_lines = [
        "const UgaLocale = require('" + npm_root + "/ug-locale')();",
        "const out = { districts: UgaLocale.districts(), counties: {}, subcounties: {}, parishes: {}, villages: {} };",
        "for (const d of out.districts) {",
        "  const counties = UgaLocale.counties(d.id);",
        "  out.counties[d.id] = counties;",
        "  for (const c of counties) {",
        "    const subs = UgaLocale.subCounties(c.id);",
        "    out.subcounties[c.id] = subs;",
        "    for (const s of subs) {",
        "      const parishes = UgaLocale.parishes(s.id);",
        "      out.parishes[s.id] = parishes;",
        "      for (const p of parishes) {",
        "        out.villages[p.id] = UgaLocale.villages(p.id);",
        "      }",
        "    }",
        "  }",
        "}",
        "process.stdout.write(JSON.stringify(out));",
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
        f.write("\n".join(js_lines))
        tmp = f.name
    try:
        result = subprocess.run(["node", tmp], capture_output=True, text=True, check=True)
    finally:
        os.unlink(tmp)

    return json.loads(result.stdout)


def title(s: str) -> str:
    return s.title()


def seed_geo() -> None:
    with Session(engine) as session:
        if session.exec(select(Region)).first():
            print("Geo data already seeded, skipping.")
            return

    print("Loading ug-locale data via Node.js…")
    data = get_ug_locale_data()

    # Build lookup: district name (upper) → ug-locale district id
    district_name_to_id = {d["name"].upper(): d["id"] for d in data["districts"]}

    print("Seeding geography…")
    with Session(engine) as session:

        # ── Regions ───────────────────────────────────────
        region_objs: dict[str, Region] = {}
        for region_name in REGION_SECTOR_DISTRICT:
            obj = session.exec(select(Region).where(Region.name == region_name)).first()
            if not obj:
                obj = Region(name=region_name)
                session.add(obj)
                session.flush()
            region_objs[region_name] = obj
        print(f"  Regions: {len(region_objs)}")

        # ── Sectors ───────────────────────────────────────
        sector_objs: dict[str, Sector] = {}
        for region_name, sectors in REGION_SECTOR_DISTRICT.items():
            region = region_objs[region_name]
            for sector_name in sectors:
                obj = session.exec(
                    select(Sector).where(
                        Sector.name == sector_name,
                        Sector.region_id == region.id,
                    )
                ).first()
                if not obj:
                    obj = Sector(name=sector_name, region_id=region.id)
                    session.add(obj)
                    session.flush()
                sector_objs[sector_name] = obj
        print(f"  Sectors: {len(sector_objs)}")

        # ── Districts ─────────────────────────────────────
        district_objs: dict[str, District] = {}  # ug-locale id → District
        district_count = 0
        for region_name, sectors in REGION_SECTOR_DISTRICT.items():
            for sector_name, district_names in sectors.items():
                sector = sector_objs[sector_name]
                for dname in district_names:
                    ug_id = district_name_to_id.get(dname.upper())
                    if not ug_id:
                        print(f"    WARNING: district '{dname}' not found in ug-locale, skipping")
                        continue
                    display_name = title(dname)
                    obj = session.exec(
                        select(District).where(
                            District.name == display_name,
                            District.sector_id == sector.id,
                        )
                    ).first()
                    if not obj:
                        obj = District(name=display_name, sector_id=sector.id)
                        session.add(obj)
                        session.flush()
                        district_count += 1
                    district_objs[ug_id] = obj
        print(f"  Districts: {district_count} new")

        # ── Counties ──────────────────────────────────────
        county_objs: dict[str, County] = {}  # ug-locale county id → County
        county_count = 0
        for ug_dist_id, district in district_objs.items():
            for c in data["counties"].get(ug_dist_id, []):
                obj = session.exec(
                    select(County).where(
                        County.name == title(c["name"]),
                        County.district_id == district.id,
                    )
                ).first()
                if not obj:
                    obj = County(name=title(c["name"]), district_id=district.id)
                    session.add(obj)
                    county_count += 1
                county_objs[c["id"]] = obj
        session.flush()
        print(f"  Counties: {county_count} new")

        # ── SubCounties ───────────────────────────────────
        subcounty_objs: dict[str, SubCounty] = {}
        subcounty_count = 0
        for ug_county_id, county in county_objs.items():
            for s in data["subcounties"].get(ug_county_id, []):
                obj = session.exec(
                    select(SubCounty).where(
                        SubCounty.name == title(s["name"]),
                        SubCounty.county_id == county.id,
                    )
                ).first()
                if not obj:
                    obj = SubCounty(name=title(s["name"]), county_id=county.id)
                    session.add(obj)
                    subcounty_count += 1
                subcounty_objs[s["id"]] = obj
        session.flush()
        print(f"  SubCounties: {subcounty_count} new")

        # ── Parishes ──────────────────────────────────────
        parish_objs: dict[str, Parish] = {}
        parish_count = 0
        for ug_sub_id, subcounty in subcounty_objs.items():
            for p in data["parishes"].get(ug_sub_id, []):
                obj = session.exec(
                    select(Parish).where(
                        Parish.name == title(p["name"]),
                        Parish.subcounty_id == subcounty.id,
                    )
                ).first()
                if not obj:
                    obj = Parish(name=title(p["name"]), subcounty_id=subcounty.id)
                    session.add(obj)
                    parish_count += 1
                parish_objs[p["id"]] = obj
        session.flush()
        print(f"  Parishes: {parish_count} new")

        # ── Villages ──────────────────────────────────────
        # ug-locale has duplicate village names within the same parish.
        # Deduplicate in-memory with a seen set, then bulk-insert via psycopg
        # executemany with ON CONFLICT DO NOTHING.
        village_count = 0
        batch: list[tuple] = []
        seen: set[tuple] = set()

        conn = session.connection().connection  # raw psycopg connection

        def _flush_villages(rows: list[tuple]) -> None:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO village (id, name, parish_id) VALUES (%s, %s, %s) "
                    "ON CONFLICT ON CONSTRAINT uq_village_name_parish DO NOTHING",
                    rows,
                )

        for ug_parish_id, parish in parish_objs.items():
            for v in data["villages"].get(ug_parish_id, []):
                key = (title(v["name"]), str(parish.id))
                if key in seen:
                    continue
                seen.add(key)
                batch.append((str(uuid.uuid4()), key[0], key[1]))
                village_count += 1
                if len(batch) >= 1000:
                    _flush_villages(batch)
                    batch = []
        if batch:
            _flush_villages(batch)
        print(f"  Villages: {village_count} new")

        session.commit()

    print("\nDone.")


if __name__ == "__main__":
    seed_geo()
