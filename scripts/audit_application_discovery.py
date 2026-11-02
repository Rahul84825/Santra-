"""
Phase F: Application Discovery Audit Script for Iteration 17.
Audits the actual SQLite records in logs/applications.db, validates existence on disk,
categorizes applications by discovery source and platform, checks broken paths,
and outputs a comprehensive JSON audit report.
"""
import os
import sys
import json
import sqlite3
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.apps.application_discovery import app_discovery

def audit_application_discovery():
    db_path = "logs/applications.db"
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT count(*) FROM discovered_applications")
    total_records = cursor.fetchone()[0]

    cursor.execute("""
        SELECT app_id, display_name, executable_path, source, platform,
               is_available, last_discovered_at, launch_mechanism
        FROM discovered_applications
    """)
    rows = cursor.fetchall()

    source_breakdown = {}
    mechanism_breakdown = {}
    valid_paths = 0
    broken_paths = []
    store_apps = []
    standard_apps = []

    for row in rows:
        app_id, display_name, exec_path, source, platform, is_available, last_disc, launch_mech = row

        source_breakdown[source] = source_breakdown.get(source, 0) + 1
        mechanism_breakdown[launch_mech] = mechanism_breakdown.get(launch_mech, 0) + 1

        # Check path validity
        # If launch_mech is uwp or packaged_app, executable_path might be an AppID or protocol
        if launch_mech in ["uwp", "packaged_app", "uri"] or "explorer.exe shell:AppsFolder" in exec_path:
            store_apps.append({"id": app_id, "name": display_name, "path": exec_path})
            valid_paths += 1
        elif os.path.exists(exec_path):
            valid_paths += 1
            standard_apps.append({"id": app_id, "name": display_name, "path": exec_path})
        elif shutil_which := shutil.which(exec_path):
            valid_paths += 1
            standard_apps.append({"id": app_id, "name": display_name, "path": shutil_which})
        else:
            broken_paths.append({"id": app_id, "name": display_name, "path": exec_path})

    conn.close()

    # Also query the live app_discovery service
    live_apps = app_discovery.get_all_applications()

    # Test launching capability verification (dry run test of resolver without opening 20 windows)
    sample_to_test = ["notepad", "calc", "chrome", "explorer"]
    launch_audit = {}
    for name in sample_to_test:
        app = app_discovery.get_application(name)
        if app:
            launch_audit[name] = {
                "found": True,
                "display_name": app.display_name,
                "executable_path": app.executable_path,
                "exists_on_disk": os.path.exists(app.executable_path) or bool(shutil.which(app.executable_path)),
                "is_available": app.is_available
            }
        else:
            launch_audit[name] = {"found": False}

    report = {
        "database_path": db_path,
        "total_records_in_db": total_records,
        "live_applications_loaded": len(live_apps),
        "source_breakdown": source_breakdown,
        "launch_mechanism_breakdown": mechanism_breakdown,
        "valid_path_count": valid_paths,
        "broken_path_count": len(broken_paths),
        "broken_paths_sample": broken_paths[:10],
        "store_app_count": len(store_apps),
        "standard_desktop_app_count": len(standard_apps),
        "sample_resolver_check": launch_audit
    }

    report_path = "logs/iteration17_application_discovery_audit.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Audit completed: {total_records} records, {valid_paths} valid paths, {len(broken_paths)} broken paths.")
    print(f"Source breakdown: {source_breakdown}")
    print(f"Report written to {report_path}")
    return report

if __name__ == "__main__":
    import shutil
    audit_application_discovery()

