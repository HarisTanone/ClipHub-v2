"""AutoCliper Tool: Hermes Social Media Schedule Management.

Dipanggil oleh Hermes toolset autocliper_schedule_list, autocliper_schedule_retry, dan autocliper_schedule_delete.
Memungkinkan Hermes Agent untuk melihat jadwal posting Repliz, meretry postingan yang gagal, atau membatalkan jadwal.
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Load .env dari HERMES_HOME
_hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
_env_file = os.path.join(_hermes_home, ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

import ac_auth


def list_schedules(page: int = 1, limit: int = 10, status: str = "") -> dict:
    """Ambil daftar jadwal posting media sosial dari Repliz."""
    try:
        path = f"/social/schedule?page={page}&limit={limit}"
        if status and status.lower() != "all":
            path += f"&status={status.lower()}"
        res = ac_auth.api_get(path)
        return res if isinstance(res, dict) else {"data": res}
    except Exception as e:
        return {"error": str(e)}


def retry_schedule(schedule_id: str) -> dict:
    """Coba kembali (retry) postingan terjadwal yang gagal."""
    try:
        res = ac_auth.api_put(f"/social/schedule/{schedule_id}/retry", {})
        return res if isinstance(res, dict) else {"success": True, "message": "Retried"}
    except Exception as e:
        return {"error": str(e)}


def delete_schedule(schedule_id: str) -> dict:
    """Batalkan / hapus postingan terjadwal."""
    try:
        res = ac_auth.api_delete(f"/social/schedule/{schedule_id}")
        return res if isinstance(res, dict) else {"success": True, "message": "Deleted"}
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="AutoCliper Social Media Schedule Tool")
    parser.add_argument(
        "--action",
        choices=["list", "retry", "delete"],
        default="list",
        help="Aksi: 'list' (tampilkan jadwal), 'retry' (coba lagi yang gagal), 'delete' (batalkan jadwal)",
    )
    parser.add_argument("--schedule-id", type=str, default="", help="ID jadwal posting")
    parser.add_argument("--status", type=str, default="", help="Filter status: pending, process, success, error, all")
    parser.add_argument("--limit", type=int, default=10, help="Jumlah jadwal yang ditampilkan (default: 10)")
    parser.add_argument("--page", type=int, default=1, help="Nomor halaman (default: 1)")
    parser.add_argument("--json", action="store_true", help="Output format JSON")

    args = parser.parse_args()

    if args.action == "retry":
        if not args.schedule_id:
            print("❌ Parameter --schedule-id diperlukan untuk aksi retry", file=sys.stderr)
            sys.exit(1)
        result = retry_schedule(args.schedule_id)
    elif args.action == "delete":
        if not args.schedule_id:
            print("❌ Parameter --schedule-id diperlukan untuk aksi delete", file=sys.stderr)
            sys.exit(1)
        result = delete_schedule(args.schedule_id)
    else:
        result = list_schedules(page=args.page, limit=args.limit, status=args.status)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if "error" in result:
        print(f"❌ Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.action == "retry":
        print(f"🔄 Berhasil me-retry jadwal ID: {args.schedule_id}")
    elif args.action == "delete":
        print(f"🗑️ Berhasil membatalkan/menghapus jadwal ID: {args.schedule_id}")
    else:
        docs = result.get("docs", [])
        total = result.get("totalDocs", len(docs))
        print(f"📅 Daftar Jadwal Posting Media Sosial (Total: {total}, Menampilkan: {len(docs)})")
        if not docs:
            print("  (Tidak ada postingan terjadwal)")
            return

        for idx, doc in enumerate(docs, 1):
            sid = doc.get("_id") or doc.get("id") or "-"
            status = doc.get("status", "unknown").upper()
            ptype = doc.get("type", "video").upper()
            sched_at = (doc.get("scheduleAt") or "")[:19].replace("T", " ")
            title = doc.get("title") or doc.get("description") or "-"
            title_short = (title[:45] + "...") if len(title) > 45 else title
            acc = doc.get("account") or {}
            acc_name = acc.get("name") or acc.get("username") or doc.get("accountId", "-")
            acc_type = (acc.get("type") or "social").upper()

            status_icon = "⏳" if status == "PENDING" else ("✅" if status == "SUCCESS" else ("❌" if status == "ERROR" else "🔄"))
            print(f"  {idx}. {status_icon} [{status}] {ptype} -> {acc_type} ({acc_name})")
            print(f"     ID: {sid}")
            print(f"     Waktu: {sched_at} UTC")
            print(f"     Konten: {title_short}")
            print()


if __name__ == "__main__":
    main()
