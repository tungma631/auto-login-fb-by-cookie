from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


DEFAULT_API = "auto"
EXTENSION_NAME = "Get Token Cookie"
POST_LOGIN_URLS = (
    "https://adsmanager.facebook.com/adsmanager/manage/ad_account_settings",
    "https://adsmanager.facebook.com/adsmanager/billing_hub/payment_settings/",
)


class AutomationError(RuntimeError):
    pass


@dataclass(frozen=True)
class AccountRow:
    row_number: int
    profile_name: str
    info: str


def expand_api_address(value: str) -> list[str]:
    value = value.strip().rstrip("/")
    if not value:
        return []
    if value.isdigit():
        value = f"http://127.0.0.1:{value}"
    elif "://" not in value:
        value = "http://" + value
    if value.endswith(("/api/v1", "/api/v3")):
        return [value]
    return [value + "/api/v1", value + "/api/v3"]


def discover_gpm_port_files() -> list[Path]:
    explicit = os.environ.get("GPM_HTTP_PORT_FILE", "").strip()
    found = [Path(explicit).expanduser()] if explicit else []
    for env_name in ("LOCALAPPDATA", "APPDATA", "PROGRAMDATA"):
        root_value = os.environ.get(env_name)
        if not root_value:
            continue
        root = Path(root_value)
        try:
            gpm_dirs = [item for item in root.iterdir() if item.is_dir() and "gpm" in item.name.lower()]
        except OSError:
            continue
        for directory in gpm_dirs:
            try:
                found.extend(directory.rglob("http.port"))
            except OSError:
                continue
    return found


def api_candidates(requested_url: str) -> list[str]:
    if requested_url.lower() != "auto":
        return expand_api_address(requested_url)

    addresses: list[str] = []
    env_url = os.environ.get("GPM_API_URL", "").strip()
    env_port = os.environ.get("GPM_API_PORT", "").strip()
    if env_url:
        addresses.extend(expand_api_address(env_url))
    if env_port:
        addresses.extend(expand_api_address(env_port))
    for port_file in discover_gpm_port_files():
        try:
            port = port_file.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            continue
        if port.isdigit() and 1 <= int(port) <= 65535:
            addresses.extend(expand_api_address(port))
    addresses.extend(
        (
            "http://127.0.0.1:9495/api/v1",
            "http://127.0.0.1:19995/api/v3",
        )
    )
    return list(dict.fromkeys(addresses))


class GpmClient:
    def __init__(self, base_url: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @classmethod
    def connect(cls, requested_url: str) -> "GpmClient":
        candidates = api_candidates(requested_url)
        errors: list[str] = []
        for candidate in candidates:
            client = cls(candidate, timeout=1.5)
            try:
                client.get("profiles")
                return client
            except AutomationError as exc:
                errors.append(f"{candidate}: {exc}")
        raise AutomationError(
            "Không tìm thấy GPM Local API. Hãy mở GPM Login hoặc chạy với "
            "--api http://127.0.0.1:PORT/api/v1. Đã thử: " + " | ".join(errors)
        )

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise AutomationError(f"Không kết nối được GPM API tại {self.base_url}: {exc}") from exc
        if not payload.get("success"):
            raise AutomationError(payload.get("message") or f"GPM API lỗi: {path}")
        return payload.get("data")

    def profiles_by_name(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        if self.base_url.endswith("/api/v3"):
            profiles = self.get("profiles") or []
            for profile in profiles:
                result.setdefault(str(profile.get("name", "")).strip(), []).append(profile)
            return result
        page = 1
        while True:
            envelope = self.get("profiles", {"page": page, "page_size": 100, "sort": 2})
            profiles = envelope.get("data", [])
            for profile in profiles:
                result.setdefault(str(profile.get("name", "")).strip(), []).append(profile)
            if page >= int(envelope.get("last_page", 1)):
                return result
            page += 1

    def start(self, profile_id: str, extension_path: Path | None = None) -> dict[str, Any]:
        params = {"skip_proxy_check": "true"}
        if extension_path:
            params["addition_args"] = f'--load-extension="{extension_path}"'
        if self.base_url.endswith("/api/v3"):
            params = {"win_scale": "0.8"}
            if extension_path:
                params["addination_args"] = f'--load-extension="{extension_path}"'
        return self.get(
            f"profiles/start/{urllib.parse.quote(profile_id)}",
            params,
        )

    def stop(self, profile_id: str) -> None:
        action = "close" if self.base_url.endswith("/api/v3") else "stop"
        self.get(f"profiles/{action}/{urllib.parse.quote(profile_id)}")


def read_accounts(path: Path) -> list[AccountRow]:
    if not path.is_file():
        raise AutomationError(f"Không tìm thấy CSV: {path}")
    csv_text, _ = read_csv_text(path)
    rows: list[AccountRow] = []
    with io.StringIO(csv_text, newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"Tên profile", "Infor", "Status"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise AutomationError("CSV phải có ba cột bắt buộc: Tên profile, Infor, Status")
        for number, raw in enumerate(reader, start=2):
            name = (raw.get("Tên profile") or "").strip()
            info = raw.get("Infor") or ""
            if not name and not info.strip():
                continue
            if not name or not info.strip():
                raise AutomationError(f"Dòng {number}: thiếu Tên profile hoặc Infor")
            if (raw.get("Status") or "").strip().lower() == "done":
                print(f"[SKIP] {name}: Status = done")
                continue
            rows.append(AccountRow(number, name, info))
    return rows


def read_csv_text(path: Path) -> tuple[str, str]:
    raw_bytes = path.read_bytes()
    try:
        return raw_bytes.decode("utf-8-sig"), "utf-8-sig"
    except UnicodeDecodeError:
        return raw_bytes.decode("cp1258"), "cp1258"


def mark_done(path: Path, row_number: int) -> None:
    csv_text, encoding = read_csv_text(path)
    with io.StringIO(csv_text, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    if "Status" not in fieldnames:
        raise AutomationError("CSV thiếu cột Status")
    row_index = row_number - 2
    if not 0 <= row_index < len(rows):
        raise AutomationError(f"Không tìm thấy dòng {row_number} để cập nhật Status")
    rows[row_index]["Status"] = "done"
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
    temp_path.replace(path)


def attach_driver(start_data: dict[str, Any]):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
    except ImportError as exc:
        raise AutomationError("Thiếu Selenium. Chạy: python -m pip install -r requirements.txt") from exc

    port = start_data.get("remote_debugging_port")
    if not port and start_data.get("remote_debugging_address"):
        port = str(start_data["remote_debugging_address"]).rsplit(":", 1)[-1]
    driver_path = start_data.get("driver_path")
    if not port or not driver_path:
        raise AutomationError("GPM không trả về remote_debugging_port/driver_path")
    options = webdriver.ChromeOptions()
    options.debugger_address = f"127.0.0.1:{port}"
    driver = webdriver.Chrome(service=Service(str(driver_path)), options=options)
    switch_to_page(driver)
    return driver


def switch_to_page(driver) -> None:
    for handle in driver.window_handles:
        try:
            driver.switch_to.window(handle)
            url = driver.current_url.lower()
            if not url.startswith("chrome-extension://") or not url.endswith(("background.html", ".js")):
                return
        except Exception:
            continue
    driver.switch_to.new_window("tab")


def discover_extension_id(driver) -> str:
    targets = driver.execute_cdp_cmd("Target.getTargets", {}).get("targetInfos", [])
    for target in targets:
        url = str(target.get("url", ""))
        if url.startswith("chrome-extension://") and url.endswith("/backgroundSendToServer.js"):
            return url.split("/")[2]

    original = driver.current_window_handle
    driver.switch_to.new_window("tab")
    try:
        driver.get("chrome://extensions/")
        time.sleep(1)
        extension_id = driver.execute_script(
            """
            const manager = document.querySelector('extensions-manager');
            const list = manager?.shadowRoot?.querySelector('extensions-item-list');
            const items = list?.shadowRoot?.querySelectorAll('extensions-item') || [];
            for (const item of items) {
              const root = item.shadowRoot;
              const name = root?.querySelector('#name')?.textContent?.trim();
              if (name === arguments[0]) return item.id;
            }
            return null;
            """,
            EXTENSION_NAME,
        )
    finally:
        driver.close()
        driver.switch_to.window(original)
    if not extension_id:
        raise AutomationError(f'Không tìm thấy extension "{EXTENSION_NAME}" trong profile')
    return str(extension_id)


def import_with_extension(driver, extension_id: str, raw_info: str, settle_seconds: float) -> None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    driver.get(f"chrome-extension://{extension_id}/popup.html")
    wait = WebDriverWait(driver, 15)
    textarea = wait.until(EC.presence_of_element_located((By.ID, "cookieResult")))
    driver.execute_script(
        "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
        textarea,
        raw_info,
    )
    wait.until(EC.element_to_be_clickable((By.ID, "btnImportCookie"))).click()
    time.sleep(settle_seconds)
    driver.get("https://www.facebook.com/")
    time.sleep(settle_seconds)


def verify_login(driver) -> tuple[bool, str]:
    cookies = driver.get_cookies()
    c_user = next((c.get("value", "") for c in cookies if c.get("name") == "c_user"), "")
    if not c_user:
        return False, "không thấy cookie c_user"
    current_url = driver.current_url.lower()
    if "checkpoint" in current_url:
        return False, "Facebook yêu cầu checkpoint"
    if "login" in current_url:
        return False, "Facebook chuyển về trang đăng nhập"
    return True, f"đã nhận phiên Facebook (UID …{c_user[-4:]})"


def open_post_login_tabs(driver) -> None:
    for url in POST_LOGIN_URLS:
        driver.switch_to.new_window("tab")
        driver.get(url)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Đăng nhập Facebook bằng cookie vào profile GPM Login")
    parser.add_argument("--csv", type=Path, default=Path(__file__).with_name("infor.csv"))
    parser.add_argument(
        "--extension",
        type=Path,
        default=Path(__file__).with_name("get-token-cookie-extension"),
        help="Thư mục extension Get Token Cookie",
    )
    parser.add_argument("--api", default=DEFAULT_API, help="GPM API URL; mặc định tự dò bản mới/cũ")
    parser.add_argument("--profile", action="append", help="Chỉ chạy profile này; có thể dùng nhiều lần")
    parser.add_argument("--settle-seconds", type=float, default=3.0)
    parser.add_argument("--stop-after", action="store_true", help="Đóng profile sau khi xử lý")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ kiểm tra CSV và ghép tên profile")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        csv_path = args.csv.resolve()
        accounts = read_accounts(csv_path)
        extension_path = args.extension.resolve()
        if not (extension_path / "manifest.json").is_file():
            raise AutomationError(f"Extension không hợp lệ: {extension_path}")
        if args.profile:
            wanted = set(args.profile)
            accounts = [row for row in accounts if row.profile_name in wanted]
            missing_filters = wanted - {row.profile_name for row in accounts}
            if missing_filters:
                raise AutomationError("Không có trong CSV: " + ", ".join(sorted(missing_filters)))
        if not accounts:
            print("Không còn profile nào cần chạy; tất cả đã có Status = done.")
            return 0

        client = GpmClient.connect(args.api)
        print(f"GPM API: {client.base_url}")
        profiles = client.profiles_by_name()
        matched: list[tuple[AccountRow, dict[str, Any]]] = []
        problems: list[str] = []
        for row in accounts:
            choices = profiles.get(row.profile_name, [])
            if len(choices) == 1:
                matched.append((row, choices[0]))
            elif not choices:
                problems.append(f"dòng {row.row_number}: không thấy profile '{row.profile_name}'")
            else:
                chosen = max(choices, key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""))
                matched.append((row, chosen))
                print(
                    f"[WARN] dòng {row.row_number}: có {len(choices)} profile tên "
                    f"'{row.profile_name}', chọn profile mới nhất"
                )

        print(f"CSV: {len(accounts)} dòng | Ghép được: {len(matched)} | Lỗi ghép: {len(problems)}")
        for problem in problems:
            print(f"[SKIP] {problem}")
        if args.dry_run:
            return 0 if not problems else 2

        successes = 0
        for index, (row, profile) in enumerate(matched, start=1):
            profile_id = str(profile["id"])
            driver = None
            print(f"[{index}/{len(matched)}] {row.profile_name}: đang mở profile...")
            try:
                start_data = client.start(profile_id, extension_path)
                driver = attach_driver(start_data)
                driver.get("https://www.facebook.com/")
                try:
                    extension_id = discover_extension_id(driver)
                except AutomationError:
                    # GPM trả session cache nếu profile đã mở; khởi động lại để nhận --load-extension.
                    driver.service.stop()
                    driver = None
                    client.stop(profile_id)
                    time.sleep(2)
                    start_data = client.start(profile_id, extension_path)
                    driver = attach_driver(start_data)
                    driver.get("https://www.facebook.com/")
                    extension_id = discover_extension_id(driver)
                import_with_extension(driver, extension_id, row.info, args.settle_seconds)
                ok, detail = verify_login(driver)
                if ok:
                    open_post_login_tabs(driver)
                    mark_done(csv_path, row.row_number)
                    detail += " | đã mở 2 tab Ads Manager"
                print(f"[{'OK' if ok else 'FAIL'}] {row.profile_name}: {detail}")
                successes += int(ok)
            except Exception as exc:
                print(f"[FAIL] {row.profile_name}: {exc}")
            finally:
                if driver is not None:
                    try:
                        if args.stop_after:
                            driver.quit()
                        else:
                            # Ngắt tiến trình chromedriver nhưng không gửi lệnh đóng browser GPM.
                            driver.service.stop()
                    except Exception:
                        pass
                if args.stop_after:
                    try:
                        client.stop(profile_id)
                    except Exception as exc:
                        print(f"[WARN] {row.profile_name}: không đóng được profile: {exc}")

        print(f"Hoàn tất: {successes}/{len(matched)} profile đăng nhập thành công")
        return 0 if successes == len(matched) and not problems else 1
    except AutomationError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
