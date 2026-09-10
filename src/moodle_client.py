import re
import json
import time
import logging
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import requests
from bs4 import BeautifulSoup

from src.config import (
    UMN_BASE_URL,
    UMN_USERNAME,
    UMN_PASSWORD,
    MATERIALS_DIR,
    COURSES_FILE,
    ASSIGNMENTS_FILE,
    SYNC_STATE_FILE,
    ASSIGNMENTS_ATTACH_DIR
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("moodle_client")

class MoodleClient:
    def __init__(self, base_url: str = UMN_BASE_URL, username: str = UMN_USERNAME, password: str = UMN_PASSWORD):
        # Sanitize base URL in case /dashboard was passed
        clean_base = re.sub(r"/dashboard/?$", "", base_url.strip()).rstrip("/")
        self.base_url = clean_base
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8"
        })
        self.is_logged_in = False
        self.dashboard_html = ""

    def sanitize_filename(self, name: str) -> str:
        """Sanitize filename to prevent invalid filesystem characters."""
        clean = re.sub(r'[\\/*?:"<>|]', "_", name).strip()
        clean = re.sub(r'\s+', ' ', clean)
        return clean[:120]

    def login(self) -> bool:
        """Log in to Moodle / E-Learning UMN."""
        login_url = f"{self.base_url}/login/index.php?degree=s1"
        logger.info(f"Opening login page: {login_url}")

        try:
            res = self.session.get(login_url, timeout=20)
            res.raise_for_status()

            soup = BeautifulSoup(res.text, "html.parser")
            logintoken_input = soup.find("input", {"name": "logintoken"})
            logintoken = logintoken_input["value"] if logintoken_input else ""

            login_data = {
                "username": self.username,
                "password": self.password,
                "logintoken": logintoken,
                "degree": "s1",
                "rememberusername": "1"
            }

            logger.info("Submitting login credentials...")
            post_res = self.session.post(login_url, data=login_data, timeout=25, allow_redirects=True)
            post_res.raise_for_status()
            self.dashboard_html = post_res.text

            # Check for account locked or errors
            if "Your account is locked" in post_res.text:
                logger.error("Akun terkunci sementara! 'Your account is locked.' Cek email student UMN.")
                self.is_logged_in = False
                return False

            if "loginerrormessage" in post_res.text or "Invalid login" in post_res.text:
                logger.error("Login gagal: Username atau password salah.")
                self.is_logged_in = False
                return False

            if "logout" in post_res.text.lower() or "dashboard" in post_res.url:
                logger.info("Login successful!")
                self.is_logged_in = True
                return True

            self.is_logged_in = True
            return True

        except Exception as e:
            logger.error(f"Error during login: {e}")
            self.is_logged_in = False
            return False

    def get_enrolled_courses(self) -> List[Dict[str, Any]]:
        """Fetch list of all enrolled courses via Moodle AJAX service and HTML fallback."""
        if not self.is_logged_in:
            if not self.login():
                return []

        courses = []
        seen_ids = set()

        # Step 1: Attempt Moodle Timeline / Course Overview AJAX
        # This returns ALL enrolled courses regardless of pagination or card limits
        res = self.session.get(f"{self.base_url}/my/", timeout=20)
        sesskey_match = re.search(r"\"sesskey\":\"([^\"]+)\"", res.text)
        sesskey = sesskey_match.group(1) if sesskey_match else ""

        if sesskey:
            ajax_classifications = ["all", "allincludinghidden", "inprogress", "future", "past"]
            for clf in ajax_classifications:
                try:
                    ajax_url = f"{self.base_url}/lib/ajax/service.php?sesskey={sesskey}&info=core_course_get_enrolled_courses_by_timeline_classification"
                    payload = [{
                        "index": 0,
                        "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
                        "args": {
                            "offset": 0,
                            "limit": 100,
                            "classification": clf,
                            "sort": "fullname"
                        }
                    }]
                    ares = self.session.post(ajax_url, json=payload, timeout=20)
                    if ares.status_code == 200:
                        data = ares.json()
                        raw_courses = data[0].get("data", {}).get("courses", [])
                        for rc in raw_courses:
                            cid = str(rc.get("id"))
                            fn = rc.get("fullname") or rc.get("shortname") or ""
                            if cid and cid not in seen_ids and len(fn) > 3:
                                seen_ids.add(cid)
                                courses.append({
                                    "id": cid,
                                    "title": fn,
                                    "url": f"{self.base_url}/course/view.php?id={cid}",
                                    "clean_name": self.sanitize_filename(fn)
                                })
                except Exception as e:
                    logger.warning(f"Error during AJAX course retrieval ({clf}): {e}")

        # Step 2: Fallback & additional HTML scan from multiple Moodle endpoints
        urls_to_try = [
            f"{self.base_url}/dashboard/",
            f"{self.base_url}/dashboard",
            f"{self.base_url}/my/",
            f"{self.base_url}/my/courses.php",
            f"{self.base_url}/user/profile.php",
            f"{self.base_url}/"
        ]

        sources = [self.dashboard_html, res.text] if self.dashboard_html else [res.text]

        for url in urls_to_try:
            try:
                hres = self.session.get(url, timeout=20)
                if hres.status_code == 200:
                    sources.append(hres.text)
            except Exception:
                pass

        for html in sources:
            soup = BeautifulSoup(html, "html.parser")
            course_links = soup.find_all("a", href=re.compile(r"/course/view\.php\?id=\d+"))
            for link in course_links:
                href = link.get("href", "")
                match = re.search(r"id=(\d+)", href)
                if match:
                    cid = str(match.group(1))
                    title = link.get_text(strip=True)
                    if cid not in seen_ids and title and len(title) > 3 and title.lower() != "view" and not title.isdigit():
                        seen_ids.add(cid)
                        courses.append({
                            "id": cid,
                            "title": title,
                            "url": f"{self.base_url}/course/view.php?id={cid}",
                            "clean_name": self.sanitize_filename(title)
                        })

        logger.info(f"Discovered {len(courses)} active courses.")
        with open(COURSES_FILE, "w", encoding="utf-8") as f:
            json.dump(courses, f, indent=2, ensure_ascii=False)

        return courses

    def sync_course_materials(self, course: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Scrape and download all documents and resources from a course."""
        cid = course["id"]
        course_name = course["clean_name"]
        course_url = course["url"]

        course_dir = MATERIALS_DIR / course_name
        course_dir.mkdir(parents=True, exist_ok=True)

        downloaded_files = []
        logger.info(f"Syncing materials for course: {course_name} (ID: {cid})")

        try:
            res = self.session.get(course_url, timeout=25)
            soup = BeautifulSoup(res.text, "html.parser")

            # Find resource, folder, assign, and url links
            activity_links = soup.find_all("a", href=re.compile(r"/mod/(resource|folder|assign|url)/view\.php\?id=\d+"))
            seen_activity_urls = set()

            for link in activity_links:
                href = link.get("href")
                if not href or href in seen_activity_urls:
                    continue
                seen_activity_urls.add(href)

                # Strip accesshide spans so filename doesn't contain screen-reader suffixes
                for hidden in link.find_all(class_=re.compile(r"accesshide")):
                    hidden.decompose()
                activity_text = self.sanitize_filename(link.get_text(strip=True))

                if "/mod/resource/view.php" in href:
                    file_info = self._download_resource(href, activity_text, course_dir)
                    if file_info:
                        downloaded_files.append(file_info)

                elif "/mod/folder/view.php" in href:
                    folder_files = self._download_folder(href, activity_text, course_dir)
                    downloaded_files.extend(folder_files)

        except Exception as e:
            logger.error(f"Error scraping course {course_name}: {e}")

        return downloaded_files

    def _download_resource(self, resource_url: str, title: str, dest_dir: Path) -> Optional[Dict[str, Any]]:
        """Download single resource file (PDF, PPTX, etc.)."""
        try:
            res = self.session.get(resource_url, stream=True, timeout=30, allow_redirects=True)
            if res.status_code != 200:
                return None

            filename = ""
            cd = res.headers.get("content-disposition", "")
            if "filename=" in cd:
                filename_match = re.search(r'filename="?([^";]+)"?', cd)
                if filename_match:
                    filename = urllib.parse.unquote(filename_match.group(1))

            if not filename:
                url_path = urllib.parse.urlparse(res.url).path
                ext = Path(url_path).suffix
                if ext:
                    filename = f"{title}{ext}"
                else:
                    ctype = res.headers.get("content-type", "")
                    if "pdf" in ctype:
                        filename = f"{title}.pdf"
                    elif "powerpoint" in ctype or "presentation" in ctype:
                        filename = f"{title}.pptx"
                    else:
                        filename = f"{title}.bin"

            filename = self.sanitize_filename(filename)
            target_path = dest_dir / filename

            if target_path.exists() and target_path.stat().st_size > 0:
                return {"title": title, "path": str(target_path), "is_new": False}

            with open(target_path, "wb") as f:
                for chunk in res.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"Downloaded: {filename}")
            return {"title": title, "path": str(target_path), "is_new": True}

        except Exception as e:
            logger.warning(f"Could not download resource {resource_url}: {e}")
            return None

    def _download_folder(self, folder_url: str, folder_name: str, dest_dir: Path) -> List[Dict[str, Any]]:
        """Download all files inside a Moodle folder activity."""
        folder_dir = dest_dir / folder_name
        folder_dir.mkdir(parents=True, exist_ok=True)
        files = []

        try:
            res = self.session.get(folder_url, timeout=20)
            soup = BeautifulSoup(res.text, "html.parser")

            file_links = soup.find_all("a", href=re.compile(r"pluginfile\.php"))
            for link in file_links:
                href = link.get("href")
                fname = self.sanitize_filename(link.get_text(strip=True))
                if not fname:
                    continue

                target_path = folder_dir / fname
                if not target_path.exists():
                    fres = self.session.get(href, stream=True, timeout=30)
                    if fres.status_code == 200:
                        with open(target_path, "wb") as f:
                            for chunk in fres.iter_content(chunk_size=8192):
                                f.write(chunk)
                        files.append({"title": fname, "path": str(target_path), "is_new": True})
                else:
                    files.append({"title": fname, "path": str(target_path), "is_new": False})
        except Exception as e:
            logger.warning(f"Failed downloading folder activity {folder_url}: {e}")

        return files

    def get_assignment_details(self, assign_url: str, course_name: str = "", title: str = "") -> Dict[str, Any]:
        """Ambil detail tugas dari halaman mod/assign: deskripsi/instruksi, jenis submission,
        dan unduh lampiran soal (PDF/DOCX/dll) ke data/assignment_attachments/."""
        if not self.is_logged_in:
            if not self.login():
                return {"description": "", "attachments": [], "submission_types": ""}

        safe_course = self.sanitize_filename(course_name or "Umum")
        safe_title = self.sanitize_filename(title or "Tugas")
        attach_dir = ASSIGNMENTS_ATTACH_DIR / safe_course / safe_title
        attach_dir.mkdir(parents=True, exist_ok=True)

        details = {"description": "", "attachments": [], "submission_types": ""}

        try:
            res = self.session.get(assign_url, timeout=25)
            soup = BeautifulSoup(res.text, "html.parser")

            # 1) Jenis submission (online text / file)
            for row in soup.find_all("tr"):
                text = row.get_text()
                if "Submission types" in text or "Jenis pengajuan" in text:
                    tds = row.find_all("td")
                    if tds:
                        details["submission_types"] = tds[-1].get_text(" ", strip=True)

            # 2) Deskripsi / intro tugas (container standar Moodle assign)
            intro = soup.select_one("div.no-overflow")
            if intro is None:
                intro = soup.select_one("[class*='boxgeneralsection']")
            if intro is None:
                intro = soup.select_one("[id^='intro']")
            if intro is None:
                intro = soup.select_one("div[role='main']")

            if intro is not None:
                # Buang tabel status & elemen form supaya deskripsi bersih
                for t in intro.find_all("table"):
                    t.decompose()
                for form in intro.find_all(["form", "button"]):
                    form.decompose()
                desc = intro.get_text("\n", strip=True)
                details["description"] = re.sub(r"\n{3,}", "\n\n", desc)[:9000]

            # 3) Lampiran soal (file yang di-link di area intro)
            scope = intro if intro is not None else soup
            seen = set()
            for link in scope.find_all("a", href=re.compile(r"pluginfile\.php")):
                href = link.get("href", "")
                if not href or href in seen:
                    continue
                seen.add(href)
                fname = link.get_text(strip=True)
                if not fname:
                    fname = urllib.parse.unquote(Path(urllib.parse.urlparse(href).path).name) or "lampiran"
                file_info = self._download_resource(href, fname, attach_dir)
                if file_info:
                    details["attachments"].append(file_info)

            logger.info(f"Detail tugas '{safe_title}': deskripsi {len(details['description'])} karakter, "
                        f"{len(details['attachments'])} lampiran")

        except Exception as e:
            logger.warning(f"Gagal mengambil detail tugas {assign_url}: {e}")

        return details

    def get_timeline_events(self) -> List[Dict[str, Any]]:
        """Fetch all upcoming action events (quizzes, assignments, etc.) directly from Moodle Timeline API."""
        if not self.is_logged_in:
            if not self.login():
                return []

        events = []
        try:
            res = self.session.get(f"{self.base_url}/my/", timeout=20)
            sesskey_match = re.search(r"\"sesskey\":\"([^\"]+)\"", res.text)
            sesskey = sesskey_match.group(1) if sesskey_match else ""

            if not sesskey:
                logger.warning("Gagal mendapatkan sesskey untuk timeline.")
                return []

            now_ts = int(time.time())
            wib = timezone(timedelta(hours=7))

            ajax_url = f"{self.base_url}/lib/ajax/service.php?sesskey={sesskey}&info=core_calendar_get_action_events_by_timesort"
            payload = [{
                "index": 0,
                "methodname": "core_calendar_get_action_events_by_timesort",
                "args": {
                    "timesortfrom": now_ts,
                    "limitnum": 50
                }
            }]

            ares = self.session.post(ajax_url, json=payload, timeout=20)
            if ares.status_code == 200:
                data = ares.json()
                raw_events = data[0].get("data", {}).get("events", []) if data else []
                for ev in raw_events:
                    modname = ev.get("modulename", "assign")
                    title = ev.get("activityname") or ev.get("name", "")
                    course_info = ev.get("course", {})
                    course_name = course_info.get("fullname") or ""
                    course_id = str(course_info.get("id") or "")

                    raw_url = ev.get("url") or ev.get("action", {}).get("url", "")
                    id_match = re.search(r"[?&]id=(\d+)", raw_url)
                    cmid = id_match.group(1) if id_match else ""
                    canonical_url = f"{self.base_url}/mod/{modname}/view.php?id={cmid}" if cmid else raw_url

                    ts = ev.get("timesort", 0)
                    dt = datetime.fromtimestamp(ts, tz=wib)
                    due_date_str = dt.strftime("%A, %d %B %Y, %H:%M WIB")

                    diff_secs = ts - now_ts
                    if diff_secs > 0:
                        days = diff_secs // 86400
                        hours = (diff_secs % 86400) // 3600
                        mins = (diff_secs % 3600) // 60
                        if days > 0:
                            remaining_str = f"{days} hari {hours} jam lagi"
                        elif hours > 0:
                            remaining_str = f"{hours} jam {mins} menit lagi"
                        else:
                            remaining_str = f"{mins} menit lagi"
                    else:
                        remaining_str = "Sudah lewat deadline"

                    events.append({
                        "id": cmid,
                        "course_id": course_id,
                        "course_name": course_name,
                        "title": title,
                        "url": canonical_url,
                        "status": "Pending",
                        "is_submitted": False,
                        "due_date": due_date_str,
                        "time_remaining": remaining_str,
                        "type": "quiz" if modname == "quiz" else "assignment",
                        "modulename": modname,
                        "timesort": ts
                    })

                logger.info(f"Timeline Moodle: {len(events)} tugas/kuis aktif ditemukan.")
        except Exception as e:
            logger.warning(f"Error fetching Moodle timeline events: {e}")

        return events

    def get_assignments(self, courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Scrape assignments & quizzes across Moodle Timeline and courses, checking deadlines & status."""
        if not self.is_logged_in:
            if not self.login():
                return []

        all_assignments = []
        seen_assign_ids = set()

        # Step 1: Ambil langsung dari Moodle Timeline API (Single Source of Truth untuk tugas & kuis aktif)
        timeline_events = self.get_timeline_events()
        for ev in timeline_events:
            ev_id = ev.get("id") or ev.get("url")
            if ev_id and ev_id not in seen_assign_ids:
                seen_assign_ids.add(ev_id)
                all_assignments.append(ev)

        # Step 2: Scan halaman course untuk mendeteksi tugas/kuis yang mungkin tidak ada di timeline
        # (misal tugas tanpa batas waktu atau jika Timeline API kosong)
        for course in courses:
            cid = course["id"]
            course_name = course["title"]
            course_url = course["url"]

            try:
                res = self.session.get(course_url, timeout=20)
                soup = BeautifulSoup(res.text, "html.parser")
                activity_links = soup.find_all("a", href=re.compile(r"/mod/(assign|quiz)/view\.php\?id=\d+"))

                for link in activity_links:
                    assign_url = link.get("href")
                    if not assign_url:
                        continue

                    # Extract assignment module ID (e.g. /mod/assign/view.php?id=12345)
                    id_match = re.search(r'[?&]id=(\d+)', assign_url)
                    assign_id = id_match.group(1) if id_match else assign_url

                    # Deduplicate: skip jika sudah diambil dari timeline atau link sebelumnya
                    if assign_id in seen_assign_ids:
                        continue
                    seen_assign_ids.add(assign_id)

                    is_quiz = "/mod/quiz/" in assign_url
                    modtype = "quiz" if is_quiz else "assign"
                    canonical_url = f"{self.base_url}/mod/{modtype}/view.php?id={assign_id}" if id_match else assign_url

                    # Strip accesshide spans (e.g. screen-reader "Assignment" text)
                    for hidden in link.find_all(class_=re.compile(r"accesshide")):
                        hidden.decompose()
                    assign_title = link.get_text(strip=True)

                    try:
                        ares = self.session.get(canonical_url, timeout=20)
                        asoup = BeautifulSoup(ares.text, "html.parser")

                        # Try to get clean canonical title from assignment page header
                        h2 = asoup.select_one("div[role='main'] h2") or asoup.find("h2")
                        if h2:
                            for hidden in h2.find_all(class_=re.compile(r"accesshide")):
                                hidden.decompose()
                            clean_h2 = h2.get_text(strip=True)
                            if clean_h2:
                                assign_title = clean_h2

                        # Safety cleanup: remove trailing screen-reader suffix if still present
                        for suffix in ["Assignment", "Tugas", "Quiz", "Kuis"]:
                            if assign_title.endswith(suffix) and len(assign_title) > len(suffix) and not assign_title.lower().startswith(suffix.lower()):
                                assign_title = assign_title[:-len(suffix)].strip()

                        submission_status = "Unknown"
                        due_date = "Not specified"
                        time_remaining = "Not specified"

                        table = asoup.find("table", class_="generaltable")
                        if table:
                            rows = table.find_all("tr")
                            for row in rows:
                                text = row.get_text()
                                text_lower = text.lower()
                                tds = row.find_all(["td", "th"])
                                if any(k in text_lower for k in ["submission status", "status pengajuan", "status tugas"]):
                                    if tds:
                                        submission_status = tds[-1].get_text(strip=True)
                                elif any(k in text_lower for k in ["due date", "batas waktu", "jatuh tempo", "tenggat"]):
                                    if tds:
                                        due_date = tds[-1].get_text(strip=True)
                                elif any(k in text_lower for k in ["time remaining", "sisa waktu"]):
                                    if tds:
                                        time_remaining = tds[-1].get_text(strip=True)

                        is_submitted = any(kw in submission_status.lower() for kw in ["submitted", "diajukan", "graded", "dinilai", "dikirim"])

                        all_assignments.append({
                            "id": assign_id,
                            "course_id": cid,
                            "course_name": course_name,
                            "title": assign_title,
                            "url": canonical_url,
                            "status": submission_status,
                            "is_submitted": is_submitted,
                            "due_date": due_date,
                            "time_remaining": time_remaining,
                            "type": "quiz" if is_quiz else "assignment",
                            "modulename": modtype
                        })
                    except Exception as e:
                        logger.warning(f"Error fetching assignment {canonical_url}: {e}")

            except Exception as e:
                logger.warning(f"Error reading assignments for course {course_name}: {e}")

        # Urutkan berdasarkan waktu deadline terdekat
        all_assignments.sort(key=lambda x: x.get("timesort", 9999999999))

        with open(ASSIGNMENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(all_assignments, f, indent=2, ensure_ascii=False)

        return all_assignments
