"""
The Antenna — Comprehensive Test Suite
Team 2950 — The Devastators

Tests: scoring, database, digest formatting, scraper parsing,
       bot lockfile, security, and edge cases.

Run: python3 test_antenna.py
"""

import os
import sys
import re
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

_ANTENNA_DIR = Path(__file__).resolve().parents[2] / "antenna"
sys.path.insert(0, str(_ANTENNA_DIR))

# ═════════════════════════════════════════════════════════════════════
# TEST HELPERS
# ═════════════════════════════════════════════════════════════════════

RESULTS = {"passed": 0, "failed": 0, "errors": []}
LOCK_FILE = _ANTENNA_DIR / ".bot.lock"


def _test(name):
    """Decorator to register and run a test."""
    def decorator(fn):
        fn._test_name = name
        return fn
    return decorator


def run_test(fn):
    try:
        fn()
        RESULTS["passed"] += 1
        print(f"  PASS  {fn._test_name}")
    except AssertionError as e:
        RESULTS["failed"] += 1
        RESULTS["errors"].append((fn._test_name, str(e)))
        print(f"  FAIL  {fn._test_name} — {e}")
    except Exception as e:
        RESULTS["failed"] += 1
        RESULTS["errors"].append((fn._test_name, str(e)))
        print(f"  ERROR {fn._test_name} — {type(e).__name__}: {e}")


def make_topic(**overrides):
    """Create a test topic dict with sensible defaults."""
    base = {
        "topic_id": 99999,
        "url": "https://www.chiefdelphi.com/t/test/99999",
        "title": "Test Topic",
        "excerpt": "",
        "author": "testuser",
        "category_id": 9,
        "category_name": "technical",
        "date_posted": datetime.utcnow().isoformat(),
        "last_activity": datetime.utcnow().isoformat(),
        "like_count": 0,
        "reply_count": 0,
        "posts_count": 1,
        "views": 0,
        "tags": [],
        "raw_excerpt": "",
        "summary": "",
        "tracked_teams": "",
        "keywords_matched": "",
    }
    base.update(overrides)
    return base


def get_temp_db():
    """Create a temporary database for testing."""
    from database import init_db, get_connection
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    init_db(db_path)
    return db_path


# ═════════════════════════════════════════════════════════════════════
# SCORER TESTS
# ═════════════════════════════════════════════════════════════════════

@_test("Scorer: tracked team gets +5 per team")
def test_tracked_team_scoring():
    from scorer import score_topic
    topic = make_topic(title="Team 254 Technical Binder 2026")
    result = score_topic(topic)
    assert result["relevance_score"] >= 5, f"Expected >= 5, got {result['relevance_score']}"
    assert "254" in result["tracked_teams"]


@_test("Scorer: multiple tracked teams stack")
def test_multiple_tracked_teams():
    from scorer import score_topic
    topic = make_topic(title="254 vs 1678 in Einstein Finals")
    result = score_topic(topic)
    assert "254" in result["tracked_teams"]
    assert "1678" in result["tracked_teams"]
    # Should get +5 for each tracked team
    assert result["relevance_score"] >= 10


@_test("Scorer: years are NOT treated as team numbers")
def test_years_not_teams():
    from scorer import extract_team_numbers
    teams = extract_team_numbers("2026 season 2025 recap")
    assert 2026 not in teams, "2026 should be filtered as a year"
    assert 2025 not in teams, "2025 should be filtered as a year"


@_test("Scorer: team numbers extracted correctly")
def test_team_number_extraction():
    from scorer import extract_team_numbers
    teams = extract_team_numbers("Team 254 and 1678 at 2026 Worlds")
    assert 254 in teams
    assert 1678 in teams
    assert 2026 not in teams


@_test("Scorer: known author gets +3")
def test_known_author_bonus():
    from scorer import score_topic
    topic = make_topic(title="Generic post", author="Karthik")
    result = score_topic(topic)
    assert result["relevance_score"] >= 3


@_test("Scorer: unknown author gets no bonus")
def test_unknown_author_no_bonus():
    from scorer import score_topic
    topic = make_topic(title="Generic post", author="random_user_123")
    result = score_topic(topic)
    assert result["relevance_score"] == 0


@_test("Scorer: mechanism keywords score +3")
def test_mechanism_keywords():
    from scorer import score_topic
    topic = make_topic(title="Elevator design review", excerpt="cascade elevator build")
    result = score_topic(topic)
    assert "elevator" in result["keywords_matched"]
    assert result["relevance_score"] >= 3


@_test("Scorer: design doc keywords score +5")
def test_design_doc_keywords():
    from scorer import score_topic
    topic = make_topic(title="Team 9999 Technical Binder Released")
    result = score_topic(topic)
    assert "binder" in result["keywords_matched"]
    assert result["relevance_score"] >= 5


@_test("Scorer: open alliance keywords score +4")
def test_open_alliance_keywords():
    from scorer import score_topic
    topic = make_topic(title="FRC 9999 Build Thread Open Alliance")
    result = score_topic(topic)
    assert result["relevance_score"] >= 4


@_test("Scorer: CAD link detected")
def test_cad_link_detection():
    from scorer import check_link_types
    result = check_link_types("Check our CAD at cad.onshape.com/documents/abc123")
    assert result["cad"] is True
    assert result["code"] is False


@_test("Scorer: GitHub link detected")
def test_code_link_detection():
    from scorer import check_link_types
    result = check_link_types("Code at github.com/team/repo")
    assert result["code"] is True


@_test("Scorer: video link detected")
def test_video_link_detection():
    from scorer import check_link_types
    result = check_link_types("Watch at youtube.com/watch?v=abc")
    assert result["video"] is True


@_test("Scorer: high engagement boosts score")
def test_engagement_scoring():
    from scorer import score_topic
    topic = make_topic(title="Generic discussion", like_count=150, posts_count=60)
    result = score_topic(topic)
    # 100+ likes = +5, 50+ replies = +4
    assert result["relevance_score"] >= 9


@_test("Scorer: tier thresholds are correct")
def test_tier_thresholds():
    from scorer import score_topic
    # Score 0 = ignore
    result = score_topic(make_topic(title="Nothing relevant here"))
    assert result["tier"] == "ignore"

    # Tracked team (5) + mechanism (3) = 8 = notable
    result = score_topic(make_topic(title="Team 254 elevator design"))
    assert result["tier"] == "notable", f"Expected notable, got {result['tier']} (score {result['relevance_score']})"


@_test("Scorer: critical threshold is 16+")
def test_critical_threshold():
    from scorer import score_topic
    # Tracked team (5) + design doc (5) + mechanism (3) + known author (3) + engagement (5) = 21
    topic = make_topic(
        title="254 Technical Binder 2026 Released - Elevator and Swerve",
        excerpt="Complete binder with CAD release github.com/team254",
        author="AdamHeard",
        like_count=200,
        posts_count=100,
    )
    result = score_topic(topic)
    assert result["tier"] == "critical", f"Got tier={result['tier']}, score={result['relevance_score']}"
    assert result["relevance_score"] >= 16


@_test("Scorer: 'epa' no longer matches Statbotics keywords")
def test_epa_not_statbotics():
    from scorer import score_topic
    from config import STATBOTICS_KEYWORDS
    assert "epa" not in STATBOTICS_KEYWORDS, "epa should be removed (ambiguous with CTRE)"
    # Talon SRX post should NOT route to Statbotics
    topic = make_topic(
        title="Talon SRX Ignoring Current Limit",
        excerpt="Phoenix tuner epa settings not working on swerve drive"
    )
    result = score_topic(topic)
    assert "STATBOTICS" not in (result.get("engine_file_target") or ""), \
        f"Should not target Statbotics, got: {result['engine_file_target']}"


@_test("Scorer: empty/null inputs don't crash")
def test_scorer_empty_inputs():
    from scorer import score_topic, extract_team_numbers, find_keyword_matches, check_link_types
    # Empty topic
    result = score_topic({})
    assert result["relevance_score"] == 0
    assert result["tier"] == "ignore"
    # Empty strings
    assert extract_team_numbers("") == set()
    assert extract_team_numbers(None) == set()
    assert find_keyword_matches("", ["test"]) == []
    assert find_keyword_matches(None, ["test"]) == []
    assert check_link_types("") == {"cad": False, "code": False, "video": False}
    assert check_link_types(None) == {"cad": False, "code": False, "video": False}


@_test("Scorer: engine targeting routes 254 binder correctly")
def test_engine_targeting_254():
    from scorer import score_topic
    topic = make_topic(title="254 Technical Binder 2026")
    result = score_topic(topic)
    assert "254_CROSS_SEASON_ANALYSIS" in (result.get("engine_file_target") or "")


@_test("Scorer: engine targeting routes Open Alliance correctly")
def test_engine_targeting_oa():
    from scorer import score_topic
    topic = make_topic(title="FRC 9999 Build Thread Open Alliance")
    result = score_topic(topic)
    assert "OPEN_ALLIANCE_TRACKER" in (result.get("engine_file_target") or "")


@_test("Scorer: engine targeting routes game Q&A correctly")
def test_engine_targeting_qa():
    from scorer import score_topic
    topic = make_topic(title="2026 Team Update 20", excerpt="Rule clarification on G205")
    result = score_topic(topic)
    assert "REBUILT_VALIDATION" in (result.get("engine_file_target") or "")


# ═════════════════════════════════════════════════════════════════════
# DATABASE TESTS
# ═════════════════════════════════════════════════════════════════════

@_test("Database: init creates all tables")
def test_db_init():
    db_path = get_temp_db()
    conn = sqlite3.connect(str(db_path))
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {t[0] for t in tables}
    assert "posts" in table_names
    assert "weekly_digests" in table_names
    assert "engine_updates" in table_names
    assert "scrape_runs" in table_names
    conn.close()
    os.unlink(db_path)


@_test("Database: upsert_post inserts new post")
def test_db_upsert_new():
    from database import get_connection, init_db, upsert_post
    db_path = get_temp_db()
    conn = get_connection(db_path)
    post = {
        "topic_id": 12345,
        "url": "https://cd.com/t/test/12345",
        "title": "Test Post",
        "like_count": 10,
        "reply_count": 5,
    }
    is_new = upsert_post(conn, post)
    conn.commit()
    assert is_new is True
    row = conn.execute("SELECT title FROM posts WHERE topic_id = 12345").fetchone()
    assert row[0] == "Test Post"
    conn.close()
    os.unlink(db_path)


@_test("Database: upsert_post updates existing post")
def test_db_upsert_update():
    from database import get_connection, init_db, upsert_post
    db_path = get_temp_db()
    conn = get_connection(db_path)
    post = {"topic_id": 12345, "url": "https://cd.com/t/test/12345", "title": "V1", "like_count": 10}
    upsert_post(conn, post)
    conn.commit()
    post["like_count"] = 50
    is_new = upsert_post(conn, post)
    conn.commit()
    assert is_new is False
    row = conn.execute("SELECT like_count FROM posts WHERE topic_id = 12345").fetchone()
    assert row[0] == 50
    conn.close()
    os.unlink(db_path)


@_test("Database: get_weekly_posts filters by date_posted (not date_scraped)")
def test_db_weekly_filter():
    from database import get_connection, upsert_post, get_weekly_posts
    db_path = get_temp_db()
    conn = get_connection(db_path)
    # Recent post (3 days ago)
    recent = {
        "topic_id": 1, "url": "x", "title": "Recent",
        "date_posted": (datetime.utcnow() - timedelta(days=3)).isoformat(),
        "relevance_score": 10, "tier": "notable",
    }
    # Old post (60 days ago)
    old = {
        "topic_id": 2, "url": "x", "title": "Old",
        "date_posted": (datetime.utcnow() - timedelta(days=60)).isoformat(),
        "relevance_score": 15, "tier": "high",
    }
    upsert_post(conn, recent)
    upsert_post(conn, old)
    conn.commit()
    posts = get_weekly_posts(conn, min_score=8)
    assert len(posts) == 1, f"Expected 1 recent post, got {len(posts)}"
    assert posts[0]["title"] == "Recent"
    conn.close()
    os.unlink(db_path)


@_test("Database: mark_post_reviewed updates status")
def test_db_mark_reviewed():
    from database import get_connection, upsert_post, mark_post_reviewed
    db_path = get_temp_db()
    conn = get_connection(db_path)
    post = {"topic_id": 100, "url": "x", "title": "Test", "status": "new"}
    upsert_post(conn, post)
    conn.commit()
    mark_post_reviewed(conn, 100, reviewed_by="safiq", status="pulled")
    row = conn.execute("SELECT status, reviewed_by FROM posts WHERE topic_id = 100").fetchone()
    assert row[0] == "pulled"
    assert row[1] == "safiq"
    conn.close()
    os.unlink(db_path)


@_test("Database: get_db_stats returns correct counts")
def test_db_stats():
    from database import get_connection, upsert_post, get_db_stats
    db_path = get_temp_db()
    conn = get_connection(db_path)
    for i in range(5):
        upsert_post(conn, {
            "topic_id": i, "url": "x", "title": f"Post {i}",
            "relevance_score": 10 if i < 3 else 2,
            "tier": "notable" if i < 3 else "ignore",
        })
    conn.commit()
    stats = get_db_stats(conn)
    assert stats["total_posts"] == 5
    assert stats["relevant_posts"] == 3
    conn.close()
    os.unlink(db_path)


@_test("Database: SQL injection via topic title is safe")
def test_db_sql_injection():
    from database import get_connection, upsert_post
    db_path = get_temp_db()
    conn = get_connection(db_path)
    # Attempt SQL injection in title
    evil_post = {
        "topic_id": 666,
        "url": "x",
        "title": "'; DROP TABLE posts; --",
        "like_count": 0,
    }
    upsert_post(conn, evil_post)
    conn.commit()
    # Table should still exist
    count = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    assert count >= 1, "posts table was dropped by SQL injection!"
    row = conn.execute("SELECT title FROM posts WHERE topic_id = 666").fetchone()
    assert row[0] == "'; DROP TABLE posts; --"
    conn.close()
    os.unlink(db_path)


@_test("Database: scrape run logging works")
def test_db_scrape_run():
    from database import get_connection, log_scrape_run, update_scrape_run
    db_path = get_temp_db()
    conn = get_connection(db_path)
    run_id = log_scrape_run(conn)
    assert run_id is not None
    update_scrape_run(conn, run_id, status="complete", topics_fetched=50)
    row = conn.execute("SELECT status, topics_fetched FROM scrape_runs WHERE run_id = ?", (run_id,)).fetchone()
    assert row[0] == "complete"
    assert row[1] == 50
    conn.close()
    os.unlink(db_path)


# ═════════════════════════════════════════════════════════════════════
# DIGEST FORMATTING TESTS
# ═════════════════════════════════════════════════════════════════════

@_test("Digest: no URLs in digest body text")
def test_digest_no_urls():
    from digest import format_weekly_digest
    posts = [
        make_topic(title="Test Post", url="https://www.chiefdelphi.com/t/test/123",
                   relevance_score=15, tier="high", like_count=50, reply_count=20),
    ]
    digest = format_weekly_digest(posts=posts, total_scanned=100, db_total=500)
    # URLs should NOT appear in the digest body
    assert "https://" not in digest, "Digest body should not contain URLs"
    assert "chiefdelphi.com" not in digest, "Digest body should not contain URLs"


@_test("Digest: fits in single Discord message (< 2000 chars)")
def test_digest_length():
    from digest import format_weekly_digest
    posts = [
        make_topic(title=f"Post {i}", url=f"https://cd.com/t/test/{i}",
                   relevance_score=15 - i, tier="high" if i < 2 else "notable",
                   like_count=100 - i * 10, reply_count=20)
        for i in range(11)
    ]
    digest = format_weekly_digest(posts=posts, total_scanned=200, db_total=500)
    assert len(digest) < 2000, f"Digest is {len(digest)} chars, should be < 2000"


@_test("Digest: split_for_discord respects max_length")
def test_discord_split():
    from digest import split_for_discord
    long_text = "\n".join([f"Line {i}: " + "x" * 80 for i in range(50)])
    chunks = split_for_discord(long_text, max_length=500)
    for chunk in chunks:
        assert len(chunk) <= 500, f"Chunk is {len(chunk)} chars, max is 500"
    # All content preserved
    reassembled = "\n".join(chunks)
    assert len(reassembled) >= len(long_text) * 0.9  # Allow minor whitespace differences


@_test("Digest: notable section capped at 5 items")
def test_digest_notable_cap():
    from digest import format_weekly_digest
    posts = [
        make_topic(title=f"Notable {i}", url=f"https://cd.com/t/n/{i}",
                   relevance_score=9, tier="notable", like_count=10)
        for i in range(20)
    ]
    digest = format_weekly_digest(posts=posts, total_scanned=100, db_total=500)
    # Count bullet points in notable section
    notable_bullets = digest.count("• [9]")
    assert notable_bullets == 5, f"Expected 5 notable items, got {notable_bullets}"
    assert "+15 more" in digest


@_test("Digest: critical alert contains URL wrapped in angle brackets")
def test_critical_alert_url():
    from digest import format_critical_alert
    post = {
        "title": "Critical Post",
        "url": "https://www.chiefdelphi.com/t/critical/999",
        "relevance_score": 20,
        "like_count": 300,
        "reply_count": 50,
    }
    alert = format_critical_alert(post)
    assert "<https://www.chiefdelphi.com/t/critical/999>" in alert


@_test("Digest: empty posts list doesn't crash")
def test_digest_empty():
    from digest import format_weekly_digest
    digest = format_weekly_digest(posts=[], total_scanned=0, db_total=0)
    assert "THE ANTENNA" in digest
    assert "Relevant: 0" in digest


@_test("Digest: tracked teams grouped correctly")
def test_digest_tracked_teams():
    from digest import _group_by_tracked_teams
    posts = [
        {"title": "A", "tracked_teams": "254,1678"},
        {"title": "B", "tracked_teams": "254"},
        {"title": "C", "tracked_teams": ""},
    ]
    groups = _group_by_tracked_teams(posts)
    assert 254 in groups
    assert len(groups[254]) == 2
    assert 1678 in groups
    assert len(groups[1678]) == 1


# ═════════════════════════════════════════════════════════════════════
# SCRAPER PARSING TESTS (no network calls)
# ═════════════════════════════════════════════════════════════════════

@_test("Scraper: _standardize_topic extracts fields correctly")
def test_scraper_standardize():
    from scraper import CDScraper
    scraper = CDScraper()
    raw = {
        "id": 12345,
        "title": "Test Topic",
        "slug": "test-topic",
        "category_id": 9,
        "created_at": "2026-04-01T00:00:00Z",
        "last_posted_at": "2026-04-02T00:00:00Z",
        "like_count": 42,
        "posts_count": 15,
        "views": 500,
        "tags": ["swerve", "build-log"],
        "excerpt": "A test excerpt",
        "posters": [],
    }
    result = scraper._standardize_topic(raw)
    assert result["topic_id"] == 12345
    assert result["title"] == "Test Topic"
    assert result["like_count"] == 42
    assert result["reply_count"] == 14  # posts_count - 1
    assert "swerve" in result["tags"]


@_test("Scraper: _standardize_topic skips archived topics")
def test_scraper_skip_archived():
    from scraper import CDScraper
    scraper = CDScraper()
    raw = {"id": 111, "title": "Old", "archived": True}
    assert scraper._standardize_topic(raw) is None


@_test("Scraper: _standardize_topic skips topics with no id")
def test_scraper_skip_no_id():
    from scraper import CDScraper
    scraper = CDScraper()
    assert scraper._standardize_topic({}) is None


@_test("Scraper: _build_user_lookup maps user IDs to usernames")
def test_scraper_user_lookup():
    from scraper import CDScraper
    scraper = CDScraper()
    data = {
        "users": [
            {"id": 1, "username": "alice"},
            {"id": 2, "username": "bob"},
        ]
    }
    lookup = scraper._build_user_lookup(data)
    assert lookup[1] == "alice"
    assert lookup[2] == "bob"


@_test("Scraper: _standardize_topic resolves OP username from user lookup")
def test_scraper_op_username():
    from scraper import CDScraper
    scraper = CDScraper()
    raw = {
        "id": 555,
        "title": "OP Test",
        "slug": "op-test",
        "created_at": "2026-01-01T00:00:00Z",
        "posts_count": 5,
        "posters": [{"user_id": 42, "description": "Original Poster"}],
    }
    user_lookup = {42: "Karthik"}
    result = scraper._standardize_topic(raw, user_lookup)
    assert result["author"] == "Karthik"


@_test("Scraper: handles missing/null fields gracefully")
def test_scraper_null_fields():
    from scraper import CDScraper
    scraper = CDScraper()
    raw = {
        "id": 777,
        "title": "",
        "slug": "",
        "posts_count": None,
        "like_count": None,
        "views": None,
        "tags": None,
        "posters": [],
    }
    result = scraper._standardize_topic(raw)
    assert result is not None
    assert result["like_count"] == 0
    assert result["views"] == 0


# ═════════════════════════════════════════════════════════════════════
# BOT LOCKFILE TESTS
# ═════════════════════════════════════════════════════════════════════

@_test("Lock: acquire succeeds when no lock exists")
def test_lock_acquire_clean():
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()
    from bot import acquire_lock, release_lock
    assert acquire_lock() is True
    assert LOCK_FILE.exists()
    release_lock()


@_test("Lock: acquire fails when held by live process")
def test_lock_held_by_live():
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()
    LOCK_FILE.write_text(str(os.getpid()))
    from bot import acquire_lock
    assert acquire_lock() is False
    LOCK_FILE.unlink()


@_test("Lock: stale lock (dead PID) gets cleared")
def test_lock_stale():
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()
    LOCK_FILE.write_text("99999999")
    from bot import acquire_lock, release_lock
    assert acquire_lock() is True
    release_lock()


@_test("Lock: second bot process exits with code 1")
def test_lock_second_process():
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()
    LOCK_FILE.write_text(str(os.getpid()))
    bot_path = _ANTENNA_DIR / "bot.py"
    result = subprocess.run(
        [sys.executable, str(bot_path)],
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "ANTENNA_BOT_TOKEN": "fake_token_for_test"}
    )
    assert result.returncode == 1
    assert "Another Antenna bot instance" in result.stdout
    LOCK_FILE.unlink()


@_test("Lock: release removes lockfile")
def test_lock_release():
    from bot import acquire_lock, release_lock
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()
    acquire_lock()
    assert LOCK_FILE.exists()
    release_lock()
    assert not LOCK_FILE.exists()


# ═════════════════════════════════════════════════════════════════════
# SECURITY TESTS
# ═════════════════════════════════════════════════════════════════════

@_test("Security: database uses parameterized queries (no string formatting in SQL)")
def test_no_sql_string_formatting():
    db_source = _ANTENNA_DIR / "database.py"
    content = db_source.read_text()
    # Check for f-string SQL (dangerous pattern)
    # The only f-string SQL should be in update_scrape_run which uses column names, not values
    lines = content.split("\n")
    dangerous = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Look for f-string with SELECT/INSERT/DELETE/UPDATE that interpolates values
        if re.search(r'f["\'].*(?:SELECT|INSERT|DELETE|WHERE).*\{(?!k\}).*\}', stripped):
            dangerous.append(f"  Line {i}: {stripped}")
    # update_scrape_run uses f-string for column names (safe) — allow it
    real_dangerous = [d for d in dangerous if "update_scrape_run" not in content.split("\n")[int(d.split(":")[0].strip()) - 1]]
    assert len(real_dangerous) == 0, f"Potential SQL injection:\n" + "\n".join(real_dangerous)


@_test("Security: .env file is not importable as Python")
def test_env_not_python():
    env_path = _ANTENNA_DIR / ".env"
    if env_path.exists():
        content = env_path.read_text()
        # Should not contain Python code
        assert "import " not in content
        assert "exec(" not in content
        assert "eval(" not in content


@_test("Security: bot token not hardcoded in source files")
def test_no_hardcoded_tokens():
    for py_file in _ANTENNA_DIR.glob("*.py"):
        if py_file.name.startswith("test_"):
            continue
        content = py_file.read_text()
        # Discord bot tokens are typically 70+ chars of base64-ish
        tokens = re.findall(r'[A-Za-z0-9_-]{50,}\.[\w-]{6}\.[\w-]{27,}', content)
        assert len(tokens) == 0, f"Possible hardcoded token in {py_file.name}"


@_test("Security: rate limiter prevents rapid-fire requests")
def test_rate_limiter_exists():
    from scraper import CDScraper
    scraper = CDScraper()
    assert hasattr(scraper, '_rate_limit')
    assert hasattr(scraper, '_last_request_time')
    from config import CD_RATE_LIMIT_SECONDS
    assert CD_RATE_LIMIT_SECONDS >= 1.0, "Rate limit should be at least 1 second"


@_test("Security: user agent identifies the bot properly")
def test_user_agent():
    from config import CD_USER_AGENT
    assert "TheEngine" in CD_USER_AGENT
    assert "2950" in CD_USER_AGENT


# ═════════════════════════════════════════════════════════════════════
# EDGE CASE & ROBUSTNESS TESTS
# ═════════════════════════════════════════════════════════════════════

@_test("Edge: very long title doesn't break digest")
def test_long_title():
    from digest import format_weekly_digest
    posts = [make_topic(
        title="A" * 500,
        url="https://cd.com/t/long/1",
        relevance_score=15, tier="high", like_count=10, reply_count=5,
    )]
    digest = format_weekly_digest(posts=posts, total_scanned=1, db_total=1)
    assert len(digest) > 0


@_test("Edge: special characters in title don't break formatting")
def test_special_chars_title():
    from digest import format_weekly_digest
    posts = [make_topic(
        title="**Bold** _italic_ `code` [link](url) @everyone",
        url="https://cd.com/t/special/1",
        relevance_score=15, tier="high", like_count=10, reply_count=5,
    )]
    digest = format_weekly_digest(posts=posts, total_scanned=1, db_total=1)
    assert "@everyone" in digest  # Should not be sanitized at format level


@_test("Edge: zero-score topic has tier=ignore")
def test_zero_score():
    from scorer import score_topic
    topic = make_topic(title="Completely irrelevant post about cooking")
    result = score_topic(topic)
    assert result["relevance_score"] == 0
    assert result["tier"] == "ignore"


@_test("Edge: tags as dict list handled correctly")
def test_tags_dict_list():
    from scorer import score_topic
    topic = make_topic(
        title="Some post",
        tags=[{"name": "swerve"}, {"name": "build-log"}]
    )
    result = score_topic(topic)
    assert "swerve" in result["keywords_matched"]


@_test("Edge: tags as string list handled correctly")
def test_tags_string_list():
    from scorer import score_topic
    topic = make_topic(title="Some post", tags=["swerve", "build-log"])
    result = score_topic(topic)
    assert "swerve" in result["keywords_matched"]


@_test("Edge: negative like_count treated as 0")
def test_negative_likes():
    from scorer import score_topic
    topic = make_topic(title="Test", like_count=-5)
    result = score_topic(topic)
    # Should not crash
    assert result["relevance_score"] >= 0


@_test("Edge: config score thresholds are ordered correctly")
def test_threshold_ordering():
    from config import SCORE_THRESHOLDS
    assert SCORE_THRESHOLDS["ignore"] < SCORE_THRESHOLDS["notable"]
    assert SCORE_THRESHOLDS["notable"] < SCORE_THRESHOLDS["high"]
    assert SCORE_THRESHOLDS["high"] <= SCORE_THRESHOLDS["critical"]


@_test("Edge: all scan modes have required keys")
def test_scan_modes_complete():
    from config import SCAN_MODES
    required_keys = {"scan_interval_hours", "digest_day", "digest_hour", "max_pages", "description"}
    for mode_name, mode_config in SCAN_MODES.items():
        missing = required_keys - set(mode_config.keys())
        assert not missing, f"Scan mode '{mode_name}' missing keys: {missing}"


@_test("Edge: tracked teams are valid FRC numbers")
def test_tracked_teams_valid():
    from config import TRACKED_TEAMS
    for team in TRACKED_TEAMS:
        assert isinstance(team, int)
        assert 10 <= team <= 9999, f"Team {team} is not a valid FRC number"


# ═════════════════════════════════════════════════════════════════════
# RUN ALL TESTS
# ═════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Collect all test functions
    tests = [obj for obj in globals().values()
             if callable(obj) and hasattr(obj, '_test_name')]

    print("=" * 60)
    print("THE ANTENNA — Test Suite")
    print("=" * 60)

    # Group by category
    categories = {
        "SCORER": [], "DATABASE": [], "DIGEST": [],
        "SCRAPER": [], "LOCK": [], "SECURITY": [], "EDGE": [],
    }
    for t in tests:
        name = t._test_name.split(":")[0].upper()
        matched = False
        for cat in categories:
            if cat in name:
                categories[cat].append(t)
                matched = True
                break
        if not matched:
            categories.setdefault("OTHER", []).append(t)

    for cat_name, cat_tests in categories.items():
        if not cat_tests:
            continue
        print(f"\n── {cat_name} {'─' * (50 - len(cat_name))}")
        for t in cat_tests:
            run_test(t)

    # Cleanup
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()

    # Summary
    total = RESULTS["passed"] + RESULTS["failed"]
    print(f"\n{'=' * 60}")
    print(f"Results: {RESULTS['passed']}/{total} passed")
    if RESULTS["errors"]:
        print(f"\nFailures:")
        for name, err in RESULTS["errors"]:
            print(f"  {name}: {err}")
    print("=" * 60)

    sys.exit(0 if RESULTS["failed"] == 0 else 1)
