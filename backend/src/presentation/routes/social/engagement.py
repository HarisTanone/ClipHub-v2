"""TikTok & Social Cross-Account Auto-Engagement (Auto Comment) via Repliz API."""
import asyncio
import datetime as dt
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.infrastructure.db_connection import get_dict_connection
from src.infrastructure.llm_router import route_chat
from src.presentation.auth_deps import get_current_user, require_superadmin
from src.presentation.routes.social.helpers import repliz_get, repliz_post

logger = logging.getLogger(__name__)

engagement_router = APIRouter(
    prefix="/engagement",
    tags=["social-engagement"],
    dependencies=[Depends(require_superadmin())]
)


def _init_engagement_db():
    """Ensure database tables exist for engagement rules, tasks, and logs."""
    try:
        conn = get_dict_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS social_engagement_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                target_account_id TEXT NOT NULL,
                target_account_name TEXT DEFAULT '',
                target_platform TEXT DEFAULT 'tiktok',
                target_mode TEXT DEFAULT 'latest',
                specific_content_id TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                delay_minutes INTEGER DEFAULT 5,
                commenters_config TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Ensure new columns exist if table was previously created
        cur.execute("PRAGMA table_info(social_engagement_rules)")
        cols = [r["name"] for r in cur.fetchall()]
        if "target_platform" not in cols:
            cur.execute("ALTER TABLE social_engagement_rules ADD COLUMN target_platform TEXT DEFAULT 'tiktok'")
        if "target_mode" not in cols:
            cur.execute("ALTER TABLE social_engagement_rules ADD COLUMN target_mode TEXT DEFAULT 'latest'")
        if "specific_content_id" not in cols:
            cur.execute("ALTER TABLE social_engagement_rules ADD COLUMN specific_content_id TEXT DEFAULT ''")
        if "delay_minutes" not in cols:
            cur.execute("ALTER TABLE social_engagement_rules ADD COLUMN delay_minutes INTEGER DEFAULT 5")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS social_engagement_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id INTEGER,
                content_id TEXT NOT NULL,
                target_account_id TEXT NOT NULL,
                target_mode TEXT DEFAULT 'latest',
                status TEXT DEFAULT 'pending',
                total_commenters INTEGER DEFAULT 0,
                completed_commenters INTEGER DEFAULT 0,
                error_message TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS social_engagement_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER DEFAULT 0,
                rule_id INTEGER DEFAULT 0,
                content_id TEXT NOT NULL,
                target_account_id TEXT NOT NULL,
                commenter_account_id TEXT NOT NULL,
                commenter_account_name TEXT DEFAULT '',
                comment_text TEXT NOT NULL,
                scheduled_at TIMESTAMP,
                executed_at TIMESTAMP,
                status TEXT DEFAULT 'pending',
                repliz_comment_id TEXT DEFAULT '',
                error_message TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("PRAGMA table_info(social_engagement_logs)")
        log_cols = [r["name"] for r in cur.fetchall()]
        if "task_id" not in log_cols:
            cur.execute("ALTER TABLE social_engagement_logs ADD COLUMN task_id INTEGER DEFAULT 0")
        if "scheduled_at" not in log_cols:
            cur.execute("ALTER TABLE social_engagement_logs ADD COLUMN scheduled_at TIMESTAMP")
        if "executed_at" not in log_cols:
            cur.execute("ALTER TABLE social_engagement_logs ADD COLUMN executed_at TIMESTAMP")

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to initialize engagement tables: {e}")


_init_engagement_db()


class CommenterConfig(BaseModel):
    accountId: str
    accountName: Optional[str] = ""
    roleCategory: Optional[str] = Field("pro", description="pro, contra, netral, apatis, hate, curious, custom")
    persona: str = Field(..., description="Prompt persona/style for LLM to generate comment")


class EngagementRulePayload(BaseModel):
    name: str
    targetAccountId: str
    targetAccountName: Optional[str] = ""
    targetPlatform: Optional[str] = Field("tiktok", description="Platform target (tiktok, instagram, etc)")
    targetMode: str = Field("latest", description="'latest' atau 'specific'")
    specificContentIds: List[str] = Field(default_factory=list, description="List content ID jika mode specific")
    specificContentId: Optional[str] = Field("", description="Backward compatibility single content ID")
    isActive: bool = True
    delayMinutes: int = Field(5, ge=0, description="Jeda menit antar user komentar")
    commenters: List[CommenterConfig] = Field(default_factory=list)


class ToggleRulePayload(BaseModel):
    isActive: bool


class GenerateCommentPreviewRequest(BaseModel):
    metadata: Dict[str, Any]
    commenters: List[CommenterConfig]


class TriggerEngagementRequest(BaseModel):
    ruleId: Optional[int] = None
    targetAccountId: Optional[str] = None
    targetMode: Optional[str] = None  # 'latest' | 'specific'
    contentId: Optional[str] = None  # Specific single contentId override
    contentIds: Optional[List[str]] = None  # Multiple contentIds override
    metadata: Optional[Dict[str, Any]] = None
    delayMinutes: Optional[int] = None
    commenters: Optional[List[CommenterConfig]] = None


ROLE_CATEGORY_PROMPTS = {
    "pro": "PERAN: PRO / MENDUKUNG. Kamu sangat setuju, hype, merasa konten ini valid parah, relate, atau memuji poin kreator.",
    "contra": "PERAN: CONTRA / MENENTANG. Kamu ga setuju, skeptis, membantah logika/klaim di video, atau punya opini berlawanan.",
    "netral": "PERAN: NETRAL. Kamu berada di tengah-tengah, observatif santai, tidak memihak, menengahi diskusi.",
    "apatis": "PERAN: TIDAK PEDULI. Kamu apatis, cuek, merasa konten ini ga penting atau heran kenapa bisa lewat fyp ('terus gue kudu gimana', 'info yg sangat tidak merubah hidup gw').",
    "hate": "PERAN: HATE COMMENT / NYINYIR. Kamu julid, salty, sarkas tipis, nyindir dengan nada nyelekit ala netizen TikTok yang suka roasting.",
    "curious": "PERAN: TANYA / PENASARAN. Kamu kepo, minta spill info lanjutan, bertanya karena belum paham atau minta penjelasan lebih lanjut.",
    "custom": "PERAN: SESUAI INSTRUKSI CUSTOM."
}


def _generate_ai_comment(video_context: Dict[str, Any], persona: str, role_category: str = "pro", other_comments: Optional[List[str]] = None) -> str:
    """Generate a realistic, context-aware TikTok comment using Jaksel/skena style LLM."""
    clean_context = {
        "title": video_context.get("title") or video_context.get("name") or "",
        "description": video_context.get("description") or video_context.get("caption") or "",
        "topic": video_context.get("topic") or "",
        "tags": video_context.get("tags") or [],
        "extra": video_context.get("extra") or {}
    }
    
    role_instruction = ROLE_CATEGORY_PROMPTS.get(role_category, ROLE_CATEGORY_PROMPTS["pro"])

    avoid_instruction = ""
    if other_comments:
        avoid_instruction = f"\nKomentar akun lain di video ini:\n" + "\n".join(f"- {c}" for c in other_comments) + "\n\nPastikan komentarmu memiliki sudut pandang, reaksi emosional, kosa kata, dan nada bicara yang sama sekali BERBEDA dari komentar di atas."

    prompt = f"""Kamu adalah pengguna TikTok asli anak muda / skena Jakarta Selatan (Jaksel) yang sedang menonton dan mengomentari video berikut.

METADATA VIDEO:
{json.dumps(clean_context, indent=2, ensure_ascii=False)}

{role_instruction}
DETAIL PERSONA:
{persona}
{avoid_instruction}

ATURAN GAYA BAHASA & CARA TYPING:
1. JANGAN PERNAH MENGGUNAKAN BAHASA BAKU (dilarang kaku seperti robot, jangan formal).
2. Gunakan gaya bahasa anak muda / skena Jakarta Selatan (campuran slang, santai, kata-kata khas seperti: 'jujurly', 'which is', 'literally', 'vibesnya', 'agak laen', 'lowkey', 'valid sih', 'relate bgt', 'anjir', 'bjir', 'plis', 'cuy', 'gais', 'ygy', 'fr', dll sesuai peranmu).
3. Cara typing: ketik santai khas netizen TikTok (kebanyakan huruf kecil/lowercase, singkatan wajar seperti 'bgt', 'gw', 'lu', 'trs', 'knp').
4. Panjang: 1 kalimat pendek atau maksimal 2 kalimat (maksimal 20 kata).
5. Penggunaan Emoji: BOLEH pakai 1 emoji khas anak muda/TikTok (seperti 😭, 💀, 🗿, 🙃, 🫠, ☕) JIKA COCOK, TAPI TIDAK SEMUA komentar harus ada emoji (sebagian komentar biarkan teks murni tanpa emoji agar natural).
6. Jangan gunakan tanda kutip, jangan sertakan penjelasan prolog apapun, jangan pakai hashtag.

Tulis komentar TikTok sekarang:"""

    try:
        reply = route_chat(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.88
        )
        reply = reply.strip().strip('"\'')
        if reply.lower().startswith("komentar:"):
            reply = reply[9:].strip()
        if reply.lower().startswith("komentar tiktok:"):
            reply = reply[16:].strip()
        return reply
    except Exception as exc:
        logger.error(f"Failed to generate AI comment: {exc}")
        return "jujurly valid sih ini, relate bgt 😭"


# Active background tasks in-memory tracker (task_id -> asyncio.Task)
_RUNNING_ENGAGEMENT_TASKS: Dict[int, asyncio.Task] = {}


async def _execute_staggered_task(task_id: int, rule_id: int, content_id: str, target_acc: str, delay_minutes: int, commenters: List[Dict[str, Any]], metadata: Dict[str, Any]):
    """Background worker for sequential staggered comments per user."""
    logger.info(f"Starting staggered engagement task {task_id} for content {content_id} ({len(commenters)} commenters, delay {delay_minutes}m)")
    generated_comments: List[str] = []

    try:
        # Mark task running
        conn = get_dict_connection()
        cur = conn.cursor()
        cur.execute("UPDATE social_engagement_tasks SET status = 'running', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()

        for idx, commenter in enumerate(commenters):
            acc_id = commenter.get("accountId")
            acc_name = commenter.get("accountName", "")
            role_category = commenter.get("roleCategory", "pro")
            persona = commenter.get("persona", "Penonton TikTok biasa yang tertarik dengan isi video")
            log_id = commenter.get("logId")

            # Staggered delay: if not the first commenter, wait delay_minutes
            if idx > 0 and delay_minutes > 0:
                wait_seconds = delay_minutes * 60
                logger.info(f"Task {task_id}: Waiting {delay_minutes} minutes ({wait_seconds}s) before commenter {idx+1}/{len(commenters)} ({acc_name})...")
                
                # Update log status to waiting_delay
                if log_id:
                    conn = get_dict_connection()
                    cur = conn.cursor()
                    cur.execute("UPDATE social_engagement_logs SET status = 'waiting_delay' WHERE id = ?", (log_id,))
                    conn.commit()
                    conn.close()

                await asyncio.sleep(wait_seconds)

            # Generate distinct comment
            comment_text = _generate_ai_comment(metadata, persona, role_category=role_category, other_comments=generated_comments)
            generated_comments.append(comment_text)

            # Post comment to Repliz
            repliz_comment_id = ""
            error_msg = ""
            status = "success"

            try:
                # Update status to posting
                if log_id:
                    conn = get_dict_connection()
                    cur = conn.cursor()
                    cur.execute("UPDATE social_engagement_logs SET status = 'posting', comment_text = ? WHERE id = ?", (comment_text, log_id))
                    conn.commit()
                    conn.close()

                repliz_res = await repliz_post(
                    f"/public/content/{content_id}/comment",
                    json_body={
                        "accountId": acc_id,
                        "text": comment_text,
                    }
                )
                repliz_comment_id = (repliz_res or {}).get("commentId", "")
            except Exception as exc:
                status = "failed"
                error_msg = str(exc)
                logger.error(f"Task {task_id} commenter {acc_id} failed: {error_msg}")

            # Update log
            now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
            conn = get_dict_connection()
            cur = conn.cursor()
            cur.execute("""
                UPDATE social_engagement_logs
                SET status = ?, comment_text = ?, repliz_comment_id = ?, error_message = ?, executed_at = ?
                WHERE id = ?
            """, (status, comment_text, repliz_comment_id, error_msg, now_iso, log_id))

            # Update task progress
            cur.execute("""
                UPDATE social_engagement_tasks
                SET completed_commenters = completed_commenters + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (task_id,))
            conn.commit()
            conn.close()

        # Task finished
        conn = get_dict_connection()
        cur = conn.cursor()
        cur.execute("UPDATE social_engagement_tasks SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()
        logger.info(f"Completed staggered engagement task {task_id} successfully")
    except asyncio.CancelledError:
        logger.warning(f"Task {task_id} was cancelled")
        conn = get_dict_connection()
        cur = conn.cursor()
        cur.execute("UPDATE social_engagement_tasks SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error(f"Task {task_id} encountered fatal error: {exc}")
        conn = get_dict_connection()
        cur = conn.cursor()
        cur.execute("UPDATE social_engagement_tasks SET status = 'failed', error_message = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (str(exc), task_id))
        conn.commit()
        conn.close()
    finally:
        _RUNNING_ENGAGEMENT_TASKS.pop(task_id, None)


@engagement_router.get("/rules")
async def list_engagement_rules(user=Depends(get_current_user)):
    """List all engagement automation rules."""
    _init_engagement_db()
    conn = get_dict_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM social_engagement_rules ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()

    result = []
    for r in rows:
        commenters = []
        try:
            commenters = json.loads(r["commenters_config"] or "[]")
        except Exception:
            pass

        # Parse specific content IDs (could be JSON array or single comma string)
        specific_raw = r["specific_content_id"] or ""
        specific_ids: List[str] = []
        if specific_raw.startswith("["):
            try:
                specific_ids = json.loads(specific_raw)
            except Exception:
                specific_ids = [specific_raw] if specific_raw else []
        elif specific_raw:
            specific_ids = [s.strip() for s in specific_raw.split(",") if s.strip()]

        result.append({
            "id": r["id"],
            "name": r["name"],
            "targetAccountId": r["target_account_id"],
            "targetAccountName": r["target_account_name"] or "",
            "targetPlatform": r["target_platform"] or "tiktok",
            "targetMode": r["target_mode"] or "latest",
            "specificContentId": specific_ids[0] if specific_ids else "",
            "specificContentIds": specific_ids,
            "isActive": bool(r["is_active"]),
            "delayMinutes": r["delay_minutes"] if r["delay_minutes"] is not None else 5,
            "commenters": commenters,
            "createdAt": r["created_at"],
            "updatedAt": r["updated_at"],
        })
    return result


@engagement_router.post("/rules")
async def create_engagement_rule(payload: EngagementRulePayload, user=Depends(get_current_user)):
    """Create a new cross-account engagement rule."""
    _init_engagement_db()
    conn = get_dict_connection()
    cur = conn.cursor()
    commenters_json = json.dumps([c.model_dump() for c in payload.commenters])

    # Store specific content IDs as JSON array string
    content_ids = payload.specificContentIds
    if not content_ids and payload.specificContentId:
        content_ids = [payload.specificContentId]
    specific_stored = json.dumps(content_ids) if content_ids else ""

    cur.execute("""
        INSERT INTO social_engagement_rules (
            name, target_account_id, target_account_name, target_platform, target_mode, specific_content_id, is_active, delay_minutes, commenters_config
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        payload.name,
        payload.targetAccountId,
        payload.targetAccountName or "",
        payload.targetPlatform or "tiktok",
        payload.targetMode,
        specific_stored,
        1 if payload.isActive else 0,
        payload.delayMinutes,
        commenters_json
    ))
    rule_id = int(cur.lastrowid or 0)
    conn.commit()
    conn.close()
    return {"id": rule_id, "message": "Rule created successfully"}


@engagement_router.put("/rules/{rule_id}")
async def update_engagement_rule(rule_id: int, payload: EngagementRulePayload, user=Depends(get_current_user)):
    """Update an existing engagement rule."""
    _init_engagement_db()
    conn = get_dict_connection()
    cur = conn.cursor()
    commenters_json = json.dumps([c.model_dump() for c in payload.commenters])

    content_ids = payload.specificContentIds
    if not content_ids and payload.specificContentId:
        content_ids = [payload.specificContentId]
    specific_stored = json.dumps(content_ids) if content_ids else ""

    cur.execute("""
        UPDATE social_engagement_rules
        SET name = ?, target_account_id = ?, target_account_name = ?, target_platform = ?, target_mode = ?, specific_content_id = ?, is_active = ?, delay_minutes = ?, commenters_config = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (
        payload.name,
        payload.targetAccountId,
        payload.targetAccountName or "",
        payload.targetPlatform or "tiktok",
        payload.targetMode,
        specific_stored,
        1 if payload.isActive else 0,
        payload.delayMinutes,
        commenters_json,
        rule_id
    ))
    conn.commit()
    conn.close()
    return {"message": "Rule updated successfully"}


@engagement_router.patch("/rules/{rule_id}/toggle")
async def toggle_engagement_rule(rule_id: int, payload: ToggleRulePayload, user=Depends(get_current_user)):
    """Toggle auto-engagement rule active/inactive."""
    _init_engagement_db()
    conn = get_dict_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE social_engagement_rules
        SET is_active = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (1 if payload.isActive else 0, rule_id))
    conn.commit()
    conn.close()
    return {"id": rule_id, "isActive": payload.isActive}


@engagement_router.delete("/rules/{rule_id}")
async def delete_engagement_rule(rule_id: int, user=Depends(get_current_user)):
    """Delete an engagement rule."""
    _init_engagement_db()
    conn = get_dict_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM social_engagement_rules WHERE id = ?", (rule_id,))
    conn.commit()
    conn.close()
    return {"message": "Rule deleted successfully"}


@engagement_router.get("/contents")
async def list_target_account_contents(
    accountId: str = Query(..., description="Target account ID"),
    limit: int = Query(20, ge=1, le=50),
    user=Depends(get_current_user)
):
    """Fetch recent posts of a target account from Repliz with thumbnails so user can select visually."""
    try:
        data = await repliz_get("/public/content", params={"accountId": accountId, "limit": limit})
        docs = data.get("docs") or []
        items = []
        for d in docs:
            medias = d.get("medias") or []
            thumbnail = ""
            if medias and isinstance(medias, list):
                m0 = medias[0] or {}
                thumbnail = m0.get("thumbnail") or m0.get("url") or ""
            items.append({
                "id": d.get("id"),
                "title": d.get("title") or "",
                "description": d.get("description") or "",
                "type": d.get("type") or "video",
                "url": d.get("url") or "",
                "thumbnail": thumbnail,
                "createdAt": d.get("createdAt") or "",
                "medias": medias,
            })
        return items
    except Exception as exc:
        logger.error(f"Failed to fetch content list for account {accountId}: {exc}")
        return []


@engagement_router.post("/generate-preview")
async def generate_comment_preview(payload: GenerateCommentPreviewRequest, user=Depends(get_current_user)):
    """Preview AI generated comments across multiple commenters with different perspectives."""
    previews = []
    generated_so_far: List[str] = []

    for c in payload.commenters:
        role_cat = c.roleCategory or "pro"
        comment = _generate_ai_comment(payload.metadata, c.persona, role_category=role_cat, other_comments=generated_so_far)
        generated_so_far.append(comment)
        previews.append({
            "accountId": c.accountId,
            "accountName": c.accountName or "",
            "roleCategory": role_cat,
            "persona": c.persona,
            "comment": comment,
        })

    return {"previews": previews}


@engagement_router.post("/trigger")
async def trigger_engagement(payload: TriggerEngagementRequest, user=Depends(get_current_user)):
    """Trigger auto-engagement task with staggered delay per user."""
    _init_engagement_db()
    conn = get_dict_connection()
    cur = conn.cursor()

    rule = None
    if payload.ruleId:
        cur.execute("SELECT * FROM social_engagement_rules WHERE id = ?", (payload.ruleId,))
        rule = cur.fetchone()
    conn.close()

    target_acc = payload.targetAccountId or (rule["target_account_id"] if rule else None)
    if not target_acc:
        raise HTTPException(status_code=400, detail="Target account ID wajib diisi")

    target_mode = payload.targetMode or (rule["target_mode"] if rule else "latest")
    delay_minutes = payload.delayMinutes if payload.delayMinutes is not None else ((rule["delay_minutes"] if rule else 5) or 5)

    commenters = []
    if payload.commenters:
        commenters = [c.model_dump() for c in payload.commenters]
    elif rule:
        try:
            commenters = json.loads(rule["commenters_config"] or "[]")
        except Exception:
            commenters = []

    if not commenters:
        raise HTTPException(status_code=400, detail="Tidak ada akun pengomentar yang dikonfigurasi")

    # Resolve target content IDs list
    target_content_ids: List[str] = []
    if payload.contentIds:
        target_content_ids = [cid.strip() for cid in payload.contentIds if cid.strip()]
    elif payload.contentId:
        target_content_ids = [payload.contentId.strip()]
    elif rule and target_mode == "specific":
        specific_raw = rule["specific_content_id"] or ""
        if specific_raw.startswith("["):
            try:
                target_content_ids = json.loads(specific_raw)
            except Exception:
                target_content_ids = [specific_raw] if specific_raw else []
        elif specific_raw:
            target_content_ids = [s.strip() for s in specific_raw.split(",") if s.strip()]

    # If mode is latest or no content_ids, fetch newest post from Repliz
    if target_mode == "latest" or not target_content_ids:
        try:
            content_list = await repliz_get("/public/content", params={"accountId": target_acc, "limit": 1})
            docs = content_list.get("docs") or []
            if not docs:
                raise HTTPException(status_code=404, detail=f"Tidak ditemukan postingan pada akun target {target_acc}")
            latest_doc = docs[0]
            target_content_ids = [latest_doc.get("id")]
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Gagal mengambil postingan terbaru dari Repliz: {exc}")

    created_tasks = []

    for content_id in target_content_ids:
        # Fetch metadata JSON from Repliz for each content
        metadata = payload.metadata or {}
        if not metadata or len(target_content_ids) > 1:
            try:
                content_detail = await repliz_get(f"/public/content/{content_id}", params={"accountId": target_acc})
                if content_detail:
                    metadata = {
                        "title": content_detail.get("title", ""),
                        "description": content_detail.get("description", ""),
                        "topic": content_detail.get("topic", ""),
                        "type": content_detail.get("type", "video"),
                        "tags": content_detail.get("tags") or [],
                    }
            except Exception as exc:
                logger.warning(f"Could not fetch metadata for content {content_id}: {exc}")

        # Create task in database
        conn = get_dict_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO social_engagement_tasks (
                rule_id, content_id, target_account_id, target_mode, status, total_commenters, completed_commenters
            ) VALUES (?, ?, ?, ?, 'pending', ?, 0)
        """, (rule["id"] if rule else None, content_id, target_acc, target_mode, len(commenters)))
        task_id = int(cur.lastrowid or 0)

        # Create pending logs with scheduled_at timestamp
        now = dt.datetime.now(dt.timezone.utc)
        enriched_commenters = []
        for i, c in enumerate(commenters):
            sched_time = now + dt.timedelta(minutes=(i * delay_minutes))
            cur.execute("""
                INSERT INTO social_engagement_logs (
                    task_id, rule_id, content_id, target_account_id, commenter_account_id, commenter_account_name,
                    comment_text, scheduled_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, '', ?, 'pending')
            """, (
                task_id,
                rule["id"] if rule else None,
                content_id,
                target_acc,
                c.get("accountId"),
                c.get("accountName", ""),
                sched_time.isoformat()
            ))
            log_id = int(cur.lastrowid or 0)
            enriched_commenters.append({**c, "logId": log_id, "scheduledAt": sched_time.isoformat()})

        conn.commit()
        conn.close()

        # Launch background async worker
        bg_task = asyncio.create_task(
            _execute_staggered_task(
                task_id=task_id,
                rule_id=rule["id"] if rule else 0,
                content_id=content_id,
                target_acc=target_acc,
                delay_minutes=delay_minutes,
                commenters=enriched_commenters,
                metadata=metadata
            )
        )
        _RUNNING_ENGAGEMENT_TASKS[task_id] = bg_task
        created_tasks.append({
            "taskId": task_id,
            "contentId": content_id,
            "totalCommenters": len(commenters),
            "delayMinutes": delay_minutes,
        })

    return {
        "tasks": created_tasks,
        "totalPosts": len(created_tasks),
        "totalCommenters": len(commenters),
        "delayMinutes": delay_minutes,
        "message": f"Engagement dijadwalkan untuk {len(created_tasks)} postingan dengan {len(commenters)} akun pengomentar (jeda {delay_minutes}m per akun)",
    }


@engagement_router.get("/tasks")
async def list_engagement_tasks(
    limit: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user)
):
    """List recent engagement background tasks."""
    _init_engagement_db()
    conn = get_dict_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM social_engagement_tasks ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@engagement_router.post("/tasks/{task_id}/cancel")
async def cancel_engagement_task(task_id: int, user=Depends(get_current_user)):
    """Cancel an active or queued engagement task."""
    bg_task = _RUNNING_ENGAGEMENT_TASKS.get(task_id)
    if bg_task and not bg_task.done():
        bg_task.cancel()

    conn = get_dict_connection()
    cur = conn.cursor()
    cur.execute("UPDATE social_engagement_tasks SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
    cur.execute("UPDATE social_engagement_logs SET status = 'cancelled' WHERE task_id = ? AND status IN ('pending', 'waiting_delay')", (task_id,))
    conn.commit()
    conn.close()
    return {"taskId": task_id, "status": "cancelled"}


@engagement_router.get("/logs")
async def list_engagement_logs(
    limit: int = Query(50, ge=1, le=200),
    taskId: Optional[int] = None,
    ruleId: Optional[int] = None,
    user=Depends(get_current_user)
):
    """List recent engagement comment logs."""
    _init_engagement_db()
    conn = get_dict_connection()
    cur = conn.cursor()
    query = "SELECT * FROM social_engagement_logs WHERE 1=1"
    params = []
    if taskId:
        query += " AND task_id = ?"
        params.append(taskId)
    if ruleId:
        query += " AND rule_id = ?"
        params.append(ruleId)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
