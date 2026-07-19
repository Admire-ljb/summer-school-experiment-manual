from __future__ import annotations

import html
import hashlib
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    Image = None
    ImageDraw = None
    ImageFont = None
    ImageOps = None


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT.parent / "\u5b9e\u9a8c\u624b\u518c"
ASSET_DIR = ROOT / "assets"
ASSET_SOURCE_DIR = ASSET_DIR / "source"
IMAGE_DIR = ASSET_DIR / "images"
IMAGE_EN_DIR = ASSET_DIR / "images-en"
VIDEO_DIR = ASSET_DIR / "videos"
IMAGE_EN_CURATED_DIR = ASSET_DIR / "images-en-curated"
TRANSLATION_CACHE = ROOT / "tools" / "translation-cache.zh-en.json"
IMAGE_OCR_CACHE = ROOT / "tools" / "image-ocr-cache.json"
FINAL_TEST_SLUG = "manual-13-project-demo"
FINAL_TEST_IMAGE_NAME = "final-comprehensive-test.png"
FINAL_TEST_ZH_SOURCE = ASSET_SOURCE_DIR / "manual-13-final-comprehensive-test-zh.png"
FINAL_TEST_EN_SOURCE = ASSET_SOURCE_DIR / "manual-13-final-comprehensive-test-en.png"
CFCLIENT_TOOLCHAIN_IMAGE_SOURCE = ASSET_SOURCE_DIR / "manual-03-cfclient-python38-toolchain.png"
CFCLIENT_TOOLCHAIN_IMAGE_NAME = "009.png"
DEMO_MATERIAL_SOURCE_DIR = ASSET_SOURCE_DIR / "demo-materials"
DEMO_VIDEO_SOURCE_DIR = ASSET_SOURCE_DIR / "demo-videos"
DEMO_MATERIALS = {
    "manual-04-multiranger": [
        {
            "source": "ranging-simple-arena.jpg",
            "name": "ranging-simple-arena.jpg",
            "zh_title": "简单围栏测距场地",
            "en_title": "Simple Ranging Arena",
            "zh_text": "封闭围栏用于形成稳定的测距边界。测试时可对照无人机与挡板之间的距离变化，检查前、后、左、右方向测距值是否随场地关系同步变化。",
            "en_text": "The enclosed arena provides stable ranging boundaries. During testing, compare the drone-to-baffle distance changes with the front, back, left, and right range readings to check whether the sensor values match the arena geometry.",
        },
    ],
    "manual-06-complex-map": [
        {
            "source": "complex-mapping-arena-reference.jpg",
            "name": "complex-mapping-arena-reference.jpg",
            "zh_title": "复杂建图场地",
            "en_title": "Complex Mapping Arena",
            "zh_text": "场地由外圈挡板和内部障碍组成，适合用于检查无人机在复杂边界中的测距覆盖、航线约束和建图完整性。",
            "en_text": "The arena consists of outer baffles and internal obstacles. It is suitable for checking ranging coverage, route constraints, and mapping completeness in a complex bounded environment.",
        },
        {
            "source": "mapping-pointcloud-result.jpg",
            "name": "mapping-pointcloud-result.jpg",
            "zh_title": "点云建图结果",
            "en_title": "Point-cloud Mapping Result",
            "zh_text": "点云轮廓应与场地外边界和内部挡板位置相对应。局部离散点可作为测距噪声、姿态扰动或遮挡影响的记录，复盘时应结合飞行轨迹一并判断。",
            "en_text": "The point-cloud contour should correspond to the outer boundary and internal baffle positions. Local scattered points can record ranging noise, attitude disturbance, or occlusion effects, and should be interpreted together with the flight trajectory during review.",
        },
    ],
    "manual-13-project-demo": [
        {
            "source": "competition-real-flight-demo.jpg",
            "name": "competition-real-flight-demo.jpg",
            "zh_title": "比赛场地飞行记录",
            "en_title": "Competition Arena Flight Record",
            "zh_text": "比赛型场地记录用于核对起飞区域、通道通过、障碍避让和返航降落等关键环节，评价时应以现场完成情况、日志和视频记录共同作为依据。",
            "en_text": "The competition-style arena record is used to check key stages such as takeoff area, corridor traversal, obstacle avoidance, and return landing. Evaluation should combine on-site completion, logs, and video records.",
        },
    ],
}
DEMO_VIDEOS = {
    "manual-05-ranging": [
        {
            "source": "manual-05-ranging/ranging-enclosed-flight.mp4",
            "name": "ranging-enclosed-flight.mp4",
            "zh_title": "封闭场地避障飞行记录",
            "en_title": "Enclosed-area Obstacle-avoidance Flight Record",
            "zh_text": "该记录用于核对无人机在围栏边界附近的速度、转向和安全距离变化，并与测距阈值日志对应分析。",
            "en_text": "This record is used to check speed, turning, and safety-distance changes near the enclosure boundary, and to compare them with the ranging-threshold logs.",
        },
    ],
    "manual-06-complex-map": [
        {
            "source": "manual-06-complex-map/complex-map-overview-flight.mp4",
            "name": "complex-map-overview-flight.mp4",
            "zh_title": "复杂场地飞行过程",
            "en_title": "Complex-area Flight Process",
            "zh_text": "该记录可与点云结果对照，检查采样区域是否覆盖外圈边界与内部障碍，并定位点云缺口或异常散点的来源。",
            "en_text": "This record can be compared with the point-cloud result to check whether the sampled area covers the outer boundary and internal obstacles, and to locate the source of point-cloud gaps or abnormal scattered points.",
        },
    ],
    "manual-11-integrated-practice": [
        {
            "source": "manual-11-integrated-practice/speed-trial-flight.mp4",
            "name": "speed-trial-flight.mp4",
            "zh_title": "竞速测试场地飞行记录",
            "en_title": "Speed Trial Arena Flight Record",
            "zh_text": "记录展示了无人机在多通道场地中的路线通过过程。复盘时可结合用时、碰撞情况、转向位置和日志数据判断路线策略是否稳定。",
            "en_text": "The record shows the drone traversing a multi-corridor arena. During review, combine elapsed time, contact events, turning positions, and log data to judge whether the route strategy is stable.",
        },
    ],
    "manual-13-project-demo": [
        {
            "source": "manual-13-project-demo/competition-route-flight.mp4",
            "name": "competition-route-flight.mp4",
            "zh_title": "综合任务飞行记录",
            "en_title": "Integrated-task Flight Record",
            "zh_text": "该记录用于复盘通道通过、障碍绕行和返航降落等关键动作，评价时应结合现场完成情况与程序日志。",
            "en_text": "This record is used to review key actions such as corridor traversal, obstacle detour, and return landing. Evaluation should combine on-site completion with program logs.",
        },
    ],
}

MAX_IMAGE_WIDTH = 1440
MAX_IMAGE_HEIGHT = 1200
OCR_MAX_IMAGE_SIDE = 800

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


@dataclass(frozen=True)
class Manual:
    slug: str
    number: int
    zh_title: str
    en_title: str
    source_name: str
    purpose: str
    preparation: tuple[str, ...]
    procedure: tuple[str, ...]
    verification: tuple[str, ...]


@dataclass(frozen=True)
class ParagraphBlock:
    text: str
    style: str
    images: tuple[str, ...]


@dataclass(frozen=True)
class TableBlock:
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class HeadingInfo:
    level: int
    zh_text: str
    en_source: str | None = None
    en_prefix: str = ""
    en_suffix: str = ""
    en_text: str | None = None


Block = ParagraphBlock | TableBlock


MANUALS = [
    Manual("manual-01-vm", 1, "\u5b89\u88c5\u914d\u7f6e\u865a\u62df\u673a", "Virtual Machine Installation and Configuration", "Day1_\u5b9e\u9a8c\u624b\u518c1-\u5b89\u88c5\u914d\u7f6e\u865a\u62df\u673a.docx", "Configure VMware Workstation and install Ubuntu 20.04 as the standard operating environment for all subsequent experiments.", ("Windows host computer with sufficient memory and disk space.", "Course Materials Package: course-materials/04_virtual_machine_resources/VMware-workstation-full-16.2.5-20904516.exe.", "Course Materials Package: course-materials/04_virtual_machine_resources/ubuntu-20.04.6-desktop-amd64.iso."), ("Install VMware Workstation and verify that the new virtual-machine wizard is available.", "Create an Ubuntu virtual machine with appropriate CPU, memory, disk, and NAT network settings.", "Install Ubuntu, perform first-boot setup, install VMware Tools, and create a clean snapshot."), ("Confirm network access from Ubuntu.", "Verify screen scaling and host-to-guest file transfer.", "Restore the clean snapshot once to confirm recovery is available.")),
    Manual("manual-02-ros", 2, "\u914d\u7f6e\u8ba4\u77e5 ROS", "ROS Configuration and Basic Concepts", "Day1_\u5b9e\u9a8c\u624b\u518c2-\u914d\u7f6e\u8ba4\u77e5ROS.docx", "Install ROS and establish the basic concepts used by later robot-control experiments.", ("Ubuntu virtual machine from Manual 1.", "Network access for package installation.", "Terminal access and basic Linux command familiarity."), ("Run the FishROS script from Course Materials Package: course-materials/02_scripts_and_code/04_fishros_install.sh.", "Start roscore and run turtlesim-related commands.", "Use ROS tools to inspect nodes, topics, graphs, and message data."), ("Explain package, node, topic, publisher, and subscriber roles.", "Run turtlesim and teleoperation successfully.", "Use rqt_graph, rqt_plot, rosnode, and rostopic for observation.")),
    Manual("manual-03-crazyflie-setup", 3, "\u521d\u6b21\u914d\u7f6e\u4e0e\u9a71\u52a8 Crazyflie \u65e0\u4eba\u673a", "Initial Crazyflie Configuration and Operation", "Day1_\u5b9e\u9a8c\u624b\u518c3-\u521d\u6b21\u914d\u7f6e\u4e0e\u9a71\u52a8crazyfile\u65e0\u4eba\u673a.docx", "Prepare the Crazyflie software and hardware connection path for safe first operation.", ("Ubuntu/ROS environment from the previous manuals.", "Crazyflie aircraft, battery, USB cable, and Crazyradio.", "Git, internet access, and the Bitcraze crazyflie-clients-python repository checked out at tag 2024.7.1 for Python 3.8 compatibility; cflib and required Python dependencies."), ("Install the Crazyflie client and required libraries.", "Configure USB permissions and radio connection settings.", "Connect to the aircraft and run conservative first-control tests."), ("Crazyflie client starts correctly.", "USB and radio connection can detect the aircraft.", "A short scripted test can be explained and stopped safely.")),
    Manual("manual-04-multiranger", 4, "\u591a\u5411\u6d4b\u8ddd\u4f20\u611f\u5668\u5b9e\u9a8c", "Multi-ranger Sensor Experiment", "Day2_\u5b9e\u9a8c\u624b\u518c1-multiranger.docx", "Read multi-direction distance measurements and connect sensor readings to basic flight behavior.", ("Crazyflie with Multi-ranger deck.", "Working cflib environment.", "Clear indoor test area with simple obstacles."), ("Connect to Crazyflie through cflib.", "Read front, back, left, right, up, and down range values.", "Use threshold rules to generate simple reactive movement."), ("Range values change consistently when obstacles move.", "Students can identify which sensor direction triggered a response.", "The reactive behavior remains inside the safety area.")),
    Manual("manual-05-ranging", 5, "\u6d4b\u8ddd\u8fdb\u9636", "Advanced Ranging Experiment", "Day2_\u5b9e\u9a8c\u624b\u518c2-\u6d4b\u8ddd\u8fdb\u9636.docx", "Extend basic range reading into mission rules and obstacle-aware flight actions.", ("Crazyflie and Multi-ranger deck.", "Validated range-reading script.", "Instructor-confirmed test area."), ("Collect range readings under several obstacle configurations.", "Implement obstacle-triggered actions such as landing, backing away, or bouncing.", "Adjust thresholds and speeds conservatively."), ("The program exits through a safe stop condition.", "Sensor logs support the observed behavior.", "The selected thresholds can be justified from the measurements.")),
    Manual("manual-06-complex-map", 6, "\u590d\u6742\u5730\u56fe\u98de\u884c\u4e0e\u5efa\u56fe", "Complex-map Flight and Mapping", "Day2_\u5b9e\u9a8c\u624b\u518c3-\u590d\u6742\u5730\u56fe\u98de\u884c\u4e0e\u5efa\u56fe.docx", "Use controlled flight and range sensing to explore a more complex obstacle map.", ("Prepared obstacle area.", "Crazyflie with relevant sensing deck.", "Mapping or logging script from the manual."), ("Inspect the map constraints and permitted flight area.", "Run the flight or mapping procedure slowly enough for stable data collection.", "Review the generated obstacle points or map-like output."), ("The flight remains within the allowed area.", "The map output reflects major walls or obstacle regions.", "Failure cases are documented with likely causes.")),
    Manual("manual-07-autonomous-mapping-review", 7, "\u81ea\u4e3b\u5efa\u56fe+\u590d\u4e60", "Autonomous Mapping and Review", "Day2_\u5b9e\u9a8c\u624b\u518c4-\u81ea\u4e3b\u5efa\u56fe+\u590d\u4e60.docx", "Consolidate the ranging and mapping workflow through an autonomous mapping review task.", ("Completed range-sensing and mapping exercises.", "Known test area and flight restrictions.", "Team notes from previous experiments."), ("Review connection, sensing, control, and mapping requirements.", "Design or modify a route that samples useful map areas.", "Run the autonomous mapping task and record the result."), ("The route is reproducible.", "The produced map or log supports the route explanation.", "Main risks and improvements are recorded objectively.")),
    Manual("manual-08-path-planning", 8, "\u8def\u5f84\u89c4\u5212\u4eff\u771f", "Path-planning Simulation", "Day3_\u5b9e\u9a8c\u624b\u518c1-\u8def\u5f84\u89c4\u5212\u4eff\u771f.docx", "Run path-planning simulation experiments and compare route-generation behavior.", ("Course Materials Package: course-materials/00_project_archives/uav_motion_planning.zip.", "Ubuntu environment with required dependencies.", "Terminal access in the project directory."), ("Prepare and build the simulation project as documented.", "Set start and goal conditions in the simulator or visualization tool.", "Run A*, RRT, RRT*, or the provided planning examples and observe outputs."), ("A route is generated for the selected task.", "The observed route can be compared across algorithms or parameters.", "Execution notes include commands, errors, and screenshots where applicable.")),
    Manual("manual-09-cflib", 9, "cflib \u5e93\u7f16\u7a0b", "cflib Programming", "Day3_\u5b9e\u9a8c\u624b\u518c2-cflib\u5e93\u7f16\u7a0b.docx", "Use cflib to structure Crazyflie connection, logging, parameter access, and command scripts.", ("Working Crazyflie connection.", "Python environment with cflib installed.", "Known radio URI or scanning procedure."), ("Initialize CRTP drivers and create a Crazyflie object.", "Use synchronized connection patterns for safer program structure.", "Read parameters or logs and send controlled commands."), ("The script connects and exits cleanly.", "Logged or printed values match the expected aircraft state.", "Motion commands are short, conservative, and explainable.")),
    Manual("manual-10-motion-commander", 10, "\u8fd0\u52a8\u63a7\u5236\u63a5\u53e3\u8fdb\u9636\u7f16\u7a0b", "Advanced Motion Commander Programming", "Day3_\u5b9e\u9a8c\u624b\u518c3-Motion Commander\u8fdb\u9636\u7f16\u7a0b.docx", "Use Motion Commander movement primitives to construct repeatable flight routines.", ("cflib script template.", "Safe test area.", "Instructor-approved height and speed parameters."), ("Create a MotionCommander context.", "Combine takeoff, landing, directional movement, turns, and pauses.", "Test short movement segments before a complete sequence."), ("The drone completes the intended primitive sequence.", "Timing, height, and distance choices are recorded.", "The program can be stopped safely if behavior deviates.")),
    Manual("manual-11-integrated-practice", 11, "\u9636\u6bb5\u7efc\u5408\u5b9e\u8df5", "Integrated Practice", "Day3_\u5b9e\u9a8c\u624b\u518c4-\u9636\u6bb5\u7efc\u5408\u5b9e\u8df5.docx", "Combine setup, sensing, planning, and control skills in a bounded practical task.", ("Completed prior manuals.", "Task area and constraints.", "Team role assignment for operation, monitoring, and recording."), ("Read the task constraints and define success criteria.", "Break the route or behavior into testable components.", "Run the integrated task and record results."), ("The task is completed within the defined constraints.", "The team can explain the selected method.", "Problems are documented with concrete evidence.")),
    Manual("manual-12-position-commander", 12, "\u4f4d\u7f6e\u63a7\u5236\u63a5\u53e3\u5b9e\u9a8c", "PositionCommander", "Day3_\u5b9e\u9a8c\u624b\u518c5-PositionCommander.docx", "Use coordinate-based commands for waypoint routes and structured spatial tasks.", ("Crazyflie setup with appropriate positioning support.", "Coordinate-frame assumptions understood before flight.", "Waypoint list or route sketch."), ("Initialize PositionCommander or the documented position-control API.", "Set default height, speed, and coordinate frame carefully.", "Execute waypoint routes such as square, cube, star, or map-based paths."), ("The coordinate route matches the intended geometry.", "The aircraft remains inside the allowed volume.", "The route can be adjusted by editing explicit coordinates.")),
    Manual("manual-13-project-demo", 13, "\u7efc\u5408\u6bd4\u8d5b\u8bf4\u660e", "Integrated Project Competition", "Day3_\u5b9e\u9a8c\u624b\u518c6-\u7efc\u5408\u9879\u76ee\u5c55\u793a\u4efb\u52a1.docx", "Present the final competition task using the course experiments as technical basis.", ("Competition objective and success criteria.", "Working code and tested hardware setup.", "Presentation evidence such as logs, route sketches, video, or screenshots."), ("Read the competition task and scoring rules.", "Implement and rehearse the workflow under safety constraints.", "Present the method, result, limitations, and improvement plan."), ("The run is executable or reproducible.", "The presentation explains method and evidence objectively.", "Safety, teamwork, and failure handling are included in the report.")),
]


def clean_output() -> None:
    for path in [ROOT / "zh", ROOT / "en", IMAGE_DIR, IMAGE_EN_DIR, VIDEO_DIR]:
        if path.exists():
            shutil.rmtree(path)
    (ROOT / "zh").mkdir(parents=True, exist_ok=True)
    (ROOT / "en").mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_EN_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)


def copy_final_test_images() -> None:
    for source, image_root in [
        (FINAL_TEST_ZH_SOURCE, IMAGE_DIR),
        (FINAL_TEST_EN_SOURCE, IMAGE_EN_DIR),
    ]:
        if not source.exists():
            raise FileNotFoundError(f"Missing final test image source: {source}")
        out_dir = image_root / FINAL_TEST_SLUG
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, out_dir / FINAL_TEST_IMAGE_NAME)


def copy_cfclient_toolchain_image() -> None:
    if not CFCLIENT_TOOLCHAIN_IMAGE_SOURCE.exists():
        raise FileNotFoundError(f"Missing cfclient toolchain image source: {CFCLIENT_TOOLCHAIN_IMAGE_SOURCE}")
    out_dir = IMAGE_DIR / "manual-03-crazyflie-setup"
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CFCLIENT_TOOLCHAIN_IMAGE_SOURCE, out_dir / CFCLIENT_TOOLCHAIN_IMAGE_NAME)


def copy_demo_material_images() -> int:
    copied = 0
    for slug, items in DEMO_MATERIALS.items():
        for item in items:
            source = DEMO_MATERIAL_SOURCE_DIR / item["source"]
            if not source.exists():
                raise FileNotFoundError(f"Missing demo material image source: {source}")
            data = optimize_image_bytes(source.read_bytes(), source.suffix.lower() or ".jpg")
            for image_root in [IMAGE_DIR, IMAGE_EN_DIR]:
                out_dir = image_root / slug
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / item["name"]).write_bytes(data)
            copied += 1
    return copied


def copy_demo_videos() -> int:
    copied = 0
    for slug, items in DEMO_VIDEOS.items():
        for item in items:
            source = DEMO_VIDEO_SOURCE_DIR / item["source"]
            if not source.exists():
                raise FileNotFoundError(f"Missing demo video source: {source}")
            out_dir = VIDEO_DIR / slug
            out_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, out_dir / item["name"])
            copied += 1
    return copied


def relationship_map(zf: zipfile.ZipFile) -> dict[str, str]:
    rels_path = "word/_rels/document.xml.rels"
    if rels_path not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read(rels_path))
    return {rel.attrib["Id"]: rel.attrib["Target"] for rel in root if "Id" in rel.attrib and "Target" in rel.attrib}


def text_from(element: ET.Element, preserve: bool = False) -> str:
    text = "".join(node.text or "" for node in element.findall(".//w:t", NS))
    if preserve:
        text = text.replace("\u00a0", " ")
    return text.rstrip() if preserve else text.strip()


def paragraph_style(paragraph: ET.Element) -> str:
    style = paragraph.find("./w:pPr/w:pStyle", NS)
    return "" if style is None else style.attrib.get(f"{{{NS['w']}}}val", "")


def optimize_image_bytes(data: bytes, suffix: str) -> bytes:
    if Image is None or ImageOps is None:
        return data
    try:
        with Image.open(BytesIO(data)) as opened:
            if opened.width <= MAX_IMAGE_WIDTH and opened.height <= MAX_IMAGE_HEIGHT:
                return data
            image = ImageOps.exif_transpose(opened)
            image.thumbnail((MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT), Image.Resampling.LANCZOS)
            output = BytesIO()
            if suffix in {".jpg", ".jpeg"}:
                if image.mode not in {"RGB", "L"}:
                    image = image.convert("RGB")
                image.save(output, format="JPEG", quality=88, optimize=True, progressive=True)
            elif suffix == ".webp":
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                image.save(output, format="WEBP", quality=88, method=6)
            else:
                if image.mode == "CMYK":
                    image = image.convert("RGB")
                image.save(output, format="PNG", optimize=True)
            optimized = output.getvalue()
            return optimized if len(optimized) < len(data) else data
    except Exception:
        return data


def copy_image(zf: zipfile.ZipFile, rels: dict[str, str], rid: str, manual: Manual, index: int) -> str | None:
    target = rels.get(rid)
    if not target:
        return None
    source_name = "word/" + target.lstrip("/")
    if source_name not in zf.namelist():
        return None
    out_dir = IMAGE_DIR / manual.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(source_name).suffix.lower() or ".png"
    out_path = out_dir / f"{index:03d}{suffix}"
    out_path.write_bytes(optimize_image_bytes(zf.read(source_name), suffix))
    return f"../assets/images/{manual.slug}/{out_path.name}"


def image_path_from_src(src: str) -> Path:
    return ROOT / src.removeprefix("../")


def image_src_from_en_path(path: Path) -> str:
    return "../" + path.relative_to(ROOT).as_posix()


def all_image_sources(extracted: dict[str, tuple[Manual, list[Block], dict[str, int]]]) -> set[str]:
    sources: set[str] = set()
    for _manual, blocks, _stats in extracted.values():
        for block in blocks:
            if isinstance(block, ParagraphBlock):
                sources.update(block.images)
    return sources


def load_image_ocr_cache() -> dict[str, list[dict[str, object]]]:
    if not IMAGE_OCR_CACHE.exists():
        return {}
    return json.loads(IMAGE_OCR_CACHE.read_text(encoding="utf-8"))


def save_image_ocr_cache(cache: dict[str, list[dict[str, object]]]) -> None:
    IMAGE_OCR_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def image_digest(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


_OCR_ENGINE = None
_OCR_UNAVAILABLE = False


def get_ocr_engine():
    global _OCR_ENGINE, _OCR_UNAVAILABLE
    if _OCR_UNAVAILABLE:
        return None
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        _OCR_UNAVAILABLE = True
        print("rapidocr-onnxruntime is not installed; English image text replacement skipped.")
        return None
    _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def ocr_image(path: Path, cache: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    if Image is None:
        return []
    digest = image_digest(path)
    if digest in cache:
        return cache[digest]
    engine = get_ocr_engine()
    if engine is None:
        cache[digest] = []
        return []
    with Image.open(path) as opened:
        image = opened.convert("RGB")
        width, height = image.size
        scale = min(1.0, OCR_MAX_IMAGE_SIDE / max(width, height))
        if scale < 1.0:
            image = image.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
        try:
            import numpy as np
            result, _elapsed = engine(np.array(image))
        except Exception:
            result, _elapsed = engine(str(path))
            scale = 1.0
    items: list[dict[str, object]] = []
    for box, text, score in result or []:
        if score < 0.5 or not has_cjk(text):
            continue
        mapped_box = [[float(x) / scale, float(y) / scale] for x, y in box]
        items.append({"box": mapped_box, "text": text.strip(), "score": float(score)})
    cache[digest] = items
    return items


def collect_image_ocr(extracted: dict[str, tuple[Manual, list[Block], dict[str, int]]]) -> dict[str, list[dict[str, object]]]:
    cache = load_image_ocr_cache()
    image_ocr: dict[str, list[dict[str, object]]] = {}
    sources = sorted(all_image_sources(extracted))
    for index, src in enumerate(sources, 1):
        path = image_path_from_src(src)
        items = ocr_image(path, cache)
        if items:
            image_ocr[src] = items
        save_image_ocr_cache(cache)
        if os.environ.get("VERBOSE_OCR") or index % 20 == 0 or index == len(sources):
            print(f"OCR checked {index}/{len(sources)} images...", flush=True)
    save_image_ocr_cache(cache)
    print(f"OCR found Chinese text in {len(image_ocr)} images.")
    return image_ocr


def collect_image_translation_texts(image_ocr: dict[str, list[dict[str, object]]]) -> set[str]:
    return {str(item["text"]).strip() for items in image_ocr.values() for item in items if str(item["text"]).strip()}


def dominant_color(image) -> tuple[int, int, int]:
    rgb = image.convert("RGB")
    rgb.thumbnail((80, 80))
    pixels = list(rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata())
    if not pixels:
        return (255, 255, 255)
    quantized = Counter((r // 16 * 16, g // 16 * 16, b // 16 * 16) for r, g, b in pixels)
    r, g, b = quantized.most_common(1)[0][0]
    return (min(255, r + 8), min(255, g + 8), min(255, b + 8))


def average_luminance(image) -> float:
    rgb = image.convert("RGB")
    rgb.thumbnail((80, 80))
    pixels = list(rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata())
    if not pixels:
        return 255
    return sum(luminance(pixel) for pixel in pixels) / len(pixels)


def luminance(color: tuple[int, int, int]) -> float:
    r, g, b = color
    return 0.299 * r + 0.587 * g + 0.114 * b


def english_font(size: int):
    if ImageFont is None:
        return None
    for font_path in [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    ]:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size)
    return ImageFont.load_default()


def text_bbox(draw, text: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def wrap_translation(text: str, draw, font, max_width: int) -> list[str]:
    words = re.split(r"\s+", text.strip())
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or text_bbox(draw, candidate, font)[0] <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines or [text]


def clean_image_translation(text: str) -> str:
    cleaned = re.sub(r"�+", "", text)
    cleaned = cleaned.replace("○", "").replace("●", "").replace("（", "(").replace("）", ")")
    cleaned = cleaned.replace("<Previous step", "Back").replace("Previous step", "Back")
    cleaned = cleaned.replace("Next(N)>", "Next").replace("Next (N)>", "Next").replace("Next step", "Next")
    cleaned = cleaned.replace("help", "Help")
    cleaned = cleaned.replace("Please enter the number in your mouth to select", "Please enter the number at the prompt to select")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > 180:
        cleaned = cleaned[:177].rstrip() + "..."
    return cleaned or "English"


def draw_translated_text(image, item: dict[str, object], cache: dict[str, str]) -> None:
    if ImageDraw is None:
        return
    source = str(item["text"]).strip()
    translated = clean_image_translation(cache.get(source, source))
    box = item["box"]
    xs = [point[0] for point in box]  # type: ignore[index]
    ys = [point[1] for point in box]  # type: ignore[index]
    x1, y1, x2, y2 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
    height = max(8, y2 - y1)
    width = max(12, x2 - x1)
    pad = max(2, int(height * 0.16))
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(image.width - 1, x2 + pad)
    y2 = min(image.height - 1, y2 + pad)
    if height < 28 and width < 150:
        target_w = min(image.width - x1 - 2, max(width + pad * 2, min(width + 44, image.width - x1 - 2)))
        target_h = min(image.height - y1 - 2, max(height + pad * 2, 22))
    else:
        grow = 1.35 if len(translated) <= max(12, len(source) * 2) else 2.25
        target_w = min(image.width - x1 - 2, max(width, int(width * grow), min(width + 180, image.width - x1 - 2)))
        target_h = min(image.height - y1 - 2, max(height, int(height * 2.2)))
    x2 = min(image.width - 1, x1 + target_w)
    y2 = min(image.height - 1, y1 + target_h)
    draw = ImageDraw.Draw(image)
    bg = dominant_color(image.crop((x1, y1, max(x2, x1 + 1), max(y2, y1 + 1))))
    fg = (0, 0, 0) if luminance(bg) > 145 else (255, 255, 255)
    max_width = max(10, x2 - x1 - 6)
    max_height = max(8, y2 - y1 - 4)
    size = min(24, max(7, int(height * 0.82)))
    lines: list[str] = [translated]
    line_height = size + 2
    while size >= 6:
        font = english_font(size)
        lines = wrap_translation(translated, draw, font, max_width)
        line_height = text_bbox(draw, "Ag", font)[1] + 3
        if line_height * len(lines) <= max_height:
            break
        size -= 1
    font = english_font(size)
    line_height = text_bbox(draw, "Ag", font)[1] + 3
    draw.rectangle((x1, y1, x2, y2), fill=bg)
    yy = y1 + 2
    for line in lines[: max(1, max_height // max(1, line_height))]:
        draw.text((x1 + 3, yy), line, fill=fg, font=font)
        yy += line_height


def should_use_translation_panel(image, items: list[dict[str, object]]) -> bool:
    if not items:
        return False
    dark_dense_terminal = average_luminance(image) < 95 and len(items) >= 4
    wide_dense_ui = image.width > image.height * 1.35 and len(items) >= 18
    very_dense = len(items) >= 28
    return dark_dense_terminal or wide_dense_ui or very_dense


def draw_translation_panel(image, items: list[dict[str, object]], cache: dict[str, str]) -> None:
    if ImageDraw is None:
        return
    bg = dominant_color(image)
    if average_luminance(image) < 95:
        bg = (48, 5, 31)
    else:
        bg = (250, 250, 250)
    fg = (255, 255, 255) if luminance(bg) < 145 else (28, 28, 28)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, image.width, image.height), fill=bg)
    ordered = sorted(items, key=lambda item: (min(point[1] for point in item["box"]), min(point[0] for point in item["box"])))  # type: ignore[index]
    lines: list[str] = []
    seen: set[str] = set()
    for item in ordered:
        source = str(item["text"]).strip()
        translated = clean_image_translation(cache.get(source, source))
        if translated.lower() in seen:
            continue
        seen.add(translated.lower())
        lines.append(translated)
    margin = max(14, image.width // 60)
    font_size = max(11, min(22, image.width // 64))
    font = english_font(font_size)
    columns = 2 if image.width > 1000 and len(lines) > 18 else 1
    column_gap = margin * 2 if columns > 1 else 0
    max_width = (image.width - margin * 2 - column_gap) // columns
    wrapped: list[str] = []
    line_groups = [wrap_translation(line, draw, font, max_width) for line in lines]
    wrapped = [line for group in line_groups for line in group]
    while font_size > 8:
        font = english_font(font_size)
        line_height = text_bbox(draw, "Ag", font)[1] + 5
        lines_per_column = max(1, (image.height - margin * 2) // line_height)
        if len(wrapped) <= lines_per_column * columns:
            break
        font_size -= 1
        font = english_font(font_size)
        line_groups = [wrap_translation(line, draw, font, max_width) for line in lines]
        wrapped = [line for group in line_groups for line in group]
    line_height = text_bbox(draw, "Ag", font)[1] + 5
    lines_per_column = max(1, (image.height - margin * 2) // line_height)
    for index, line in enumerate(wrapped[: lines_per_column * columns]):
        column = index // lines_per_column
        row = index % lines_per_column
        x = margin + column * (max_width + column_gap)
        y = margin + row * line_height
        draw.text((x, y), line, fill=fg, font=font)


def build_english_images(image_ocr: dict[str, list[dict[str, object]]], cache: dict[str, str]) -> dict[str, str]:
    if Image is None:
        return {}
    image_map: dict[str, str] = {}
    for src, items in sorted(image_ocr.items()):
        source_path = image_path_from_src(src)
        relative = source_path.relative_to(IMAGE_DIR)
        out_path = IMAGE_EN_DIR / relative
        curated_path = IMAGE_EN_CURATED_DIR / relative
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if curated_path.exists():
            shutil.copyfile(curated_path, out_path)
            image_map[src] = image_src_from_en_path(out_path)
            continue
        with Image.open(source_path) as opened:
            image = opened.convert("RGB")
        if should_use_translation_panel(image, items):
            draw_translation_panel(image, items, cache)
        else:
            for item in items:
                draw_translated_text(image, item, cache)
        suffix = out_path.suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            image.save(out_path, format="JPEG", quality=90, optimize=True, progressive=True)
        else:
            image.save(out_path, format="PNG", optimize=True)
        image_map[src] = image_src_from_en_path(out_path)
    return image_map


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def is_code_like(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.startswith(("http://", "https://")):
        return True
    if re.match(r"^(sudo|pip|python|python3|ros|rosrun|roslaunch|catkin|source|git|cd|mkdir|touch|cat|ping|reboot)\b", stripped):
        return True
    if stripped in {"EOF", "EOT"}:
        return True
    if re.match(r"^(import\b|from\b|def\b|class\b|if __name__|for |while |with |try:|except|return\b|print\(|#)", stripped):
        return True
    if re.match(r"^(SUBSYSTEM==|[a-z_][a-z0-9_]*\([^)]*\)\s*/\s*[a-z_][a-z0-9_]*\()", stripped):
        return True
    return False


def is_code_style(style: str) -> bool:
    return style.strip().lower() in {"html", "code", "sourcecode", "source code"}


def is_code_candidate(block: Block) -> bool:
    return (
        isinstance(block, ParagraphBlock)
        and not block.images
        and (is_code_style(block.style) or (bool(block.text.strip()) and is_code_like(block.text)))
    )


def is_code_block(block: Block) -> bool:
    return is_code_candidate(block) and bool(block.text.strip())


CODE_COMPLETIONS = {
    "def move_linear_simple(scf):\n    ...": """def move_linear_simple(scf):
    with MotionCommander(scf, default_height=DEFAULT_HEIGHT) as mc:
        time.sleep(1)
        mc.forward(0.5)
        time.sleep(1)
        mc.back(0.5)
        time.sleep(1)""",
    "def take_off_simple(scf):\n    ...": """def take_off_simple(scf):
    with MotionCommander(scf, default_height=DEFAULT_HEIGHT):
        time.sleep(2)""",
    "def log_pos_callback(timestamp, data, logconf):\n    ...": """def log_pos_callback(timestamp, data, logconf):
    print(data)
    global position_estimate
    position_estimate[0] = data['stateEstimate.x']
    position_estimate[1] = data['stateEstimate.y']""",
    "def param_deck_flow(name, value_str):\n    ...": """def param_deck_flow(name, value_str):
    value = int(value_str)
    print(value)
    if value:
        deck_attached_event.set()
        print('Deck is attached!')
    else:
        print('Deck is NOT attached!')""",
}


CODE_TEXT_REPLACEMENTS = {
    "radio://0/60/2M/注意改成对的硬件地址": "radio://0/80/2M/E7E7E7E7E7",
    "radio://0/80/2M/注意改成对的硬件地址": "radio://0/80/2M/E7E7E7E7E7",
    "radio://0/80/2M/E7E7E7E3改成正确的硬件地址": "radio://0/80/2M/E7E7E7E7E7",
    "radio://0/80/2M/E7E7E7E7E3改成正确的硬件地址": "radio://0/80/2M/E7E7E7E7E7",
    "# 只要可以继续飞行就循环执行": "# Continue the loop while flight is allowed",
    "# 检查上方有没有障碍物": "# Check whether an obstacle is above the drone",
    "#有障碍物！停止飞行": "# Obstacle detected; stop flying",
    "# 检查前方有没有障碍物": "# Check whether an obstacle is in front of the drone",
    "# 命令无人机以设定速度飞行": "# Command the drone to fly at the configured speed",
}


def normalize_code_text(code: str) -> str:
    code = code.replace("\u00a0", " ")
    code = code.replace("\n(...)\n", "\n")
    code = code.replace(
        "\nif len(sys.argv) > 1:\n"
        "    URI = sys.argv[1]",
        "",
    )
    code = code.replace(
        "def move_box_limit(scf):\n"
        "    with MotionCommander(scf, default_height=DEFAULT_HEIGHT) as mc:\n"
        "        while (1):",
        "def move_box_limit(scf):\n"
        "    with MotionCommander(scf, default_height=DEFAULT_HEIGHT) as mc:\n"
        "        mc.start_forward()\n"
        "        while True:",
    )
    code = code.replace(
        "            elif position_estimate[0] < -BOX_LIMIT:\n"
        "                mc.start_forward()\n"
        "def move_linear_simple(scf):",
        "            elif position_estimate[0] < -BOX_LIMIT:\n"
        "                mc.start_forward()\n"
        "            time.sleep(0.1)\n"
        "def move_linear_simple(scf):",
    )
    for source, replacement in CODE_TEXT_REPLACEMENTS.items():
        code = code.replace(source, replacement)
    for placeholder, replacement in CODE_COMPLETIONS.items():
        code = code.replace(placeholder, replacement)
    return code


def load_translation_cache() -> dict[str, str]:
    if not TRANSLATION_CACHE.exists():
        return {}
    return json.loads(TRANSLATION_CACHE.read_text(encoding="utf-8"))


def save_translation_cache(cache: dict[str, str]) -> None:
    TRANSLATION_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TRANSLATION_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def translation_opener() -> urllib.request.OpenerDirector:
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or "http://127.0.0.1:7888"
    return urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))


def translate_remote(text: str, opener: urllib.request.OpenerDirector) -> str:
    query = urllib.parse.quote(text)
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=zh-CN&tl=en&dt=t&q={query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(4):
        try:
            with opener.open(request, timeout=30) as response:
                payload = response.read().decode("utf-8")
            data = json.loads(payload)
            translated = "".join(part[0] for part in data[0] if part and part[0])
            return translated.strip() or text
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            if attempt == 3:
                return text
            time.sleep(1.5 * (attempt + 1))
    return text


def should_translate(text: str) -> bool:
    stripped = text.strip()
    if not stripped or not has_cjk(stripped):
        return False
    if is_code_like(stripped):
        return stripped.startswith("#") or "#" in stripped
    return True


def ensure_translations(texts: set[str]) -> dict[str, str]:
    cache = load_translation_cache()
    pending = sorted(text for text in texts if should_translate(text) and text not in cache)
    if not pending:
        return cache

    opener = translation_opener()
    completed = 0
    print(f"Translating {len(pending)} text blocks for English pages...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(translate_remote, text, opener): text for text in pending}
        for future in as_completed(futures):
            source = futures[future]
            cache[source] = future.result()
            completed += 1
            if completed % 50 == 0 or completed == len(pending):
                save_translation_cache(cache)
                print(f"Translated {completed}/{len(pending)}")
    return cache


def english_text(text: str, cache: dict[str, str]) -> str:
    if not should_translate(text):
        return text
    return cache.get(text, text)


def is_source_manual_heading(text: str) -> bool:
    return re.match(r"^实验手册\s*\d+\s*[—–-]+", text.strip()) is not None


SECTION_HEADINGS = {
    "实验目标": ("一、实验目标", "1. Experimental goals"),
    "实验准备": ("二、实验准备", "2. Experimental preparation"),
    "实验步骤": ("三、实验步骤", "3. Experimental steps"),
    "实验验证与测试": ("四、实验验证与测试", "4. Experimental verification and testing"),
    "实验总结与拓展": ("五、实验总结与拓展", "5. Experiment summary and extension"),
    "链接资料整理": ("链接资料整理", "Reference links"),
}


CHINESE_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


STANDALONE_H2 = {
    "实验内容",
    "复习",
    "创意板块",
    "竞速板块",
    "最终综合展示评价说明",
}


TOP_LEVEL_NUMBERED_H2 = {
    "阶段综合实践说明",
    "实践任务",
    "综合项目展示任务说明",
    "任务内容",
}


GOAL_ITEM_PREFIXES = (
    "理解",
    "掌握",
    "编写",
    "学习",
    "熟悉",
    "成功",
    "通过",
    "能够",
    "继续",
    "使用",
)


STANDALONE_H3 = {
    "硬件要求",
    "软件资源（可从官网下载，为节省时间由助教拷贝）",
    "工具准备",
    "下载与安装",
    "验证安装",
    "新建虚拟机向导",
    "命名与存储",
    "硬件配置",
    "加载ISO镜像",
    "启动虚拟机",
    "系统安装流程",
    "系统初始化",
    "安装VMware Tools",
    "网络连通性测试",
    "快照恢复测试",
    "核心知识点回顾",
    "拓展任务（选做）",
    "如何读懂LED灯的含义",
    "程序执行流程",
    "核心部件",
    "起飞功能",
    "前进、转弯和后退",
    "记录飞行数据",
    "来回游荡",
    "重要注意事项！！！",
    "代码范例",
    "关键参数",
    "参数详解",
    "提示",
    "两种方式",
}


HEADING_TRANSLATIONS = {
    "阶段综合实践说明": "Stage integrated practice instructions",
    "实践任务": "Practice tasks",
    "综合项目展示任务说明": "Integrated project demonstration task description",
    "任务内容": "Task content",
    "创意板块": "Creative task section",
    "竞速板块": "Speed task section",
    "题目说明": "Task description",
    "展示流程": "Demonstration procedure",
    "评价标准细则": "Detailed evaluation criteria",
    "展示评价说明": "Demonstration evaluation instructions",
    "展示建议": "Demonstration suggestions",
    "最终综合展示评价说明": "Final integrated demonstration evaluation",
    "实验内容": "Experiment content",
    "复习": "Review",
    "程序执行流程": "Program execution flow",
    "核心部件": "Core components",
    "重要注意事项！！！": "Important notes",
    "代码范例": "Code example",
    "关键参数": "Key parameters",
    "参数详解": "Parameter details",
    "提示": "Tip",
    "两种方式": "Two methods",
    "花样飞行": "Pattern flight",
    "巡航飞行": "Cruise flight",
}


def normalized_section_heading(text: str) -> str | None:
    stripped = text.strip().rstrip(":：")
    stripped = re.sub(r"^[一二三四五六七八九十]+[、.．]\s*", "", stripped)
    stripped = re.sub(r"^\d+[.)、.．]\s*", "", stripped)
    return stripped if stripped in SECTION_HEADINGS else None


def chinese_number_to_int(text: str) -> int | None:
    if not text:
        return None
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = CHINESE_DIGITS.get(left, 1) if left else 1
        ones = CHINESE_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    return CHINESE_DIGITS.get(text)


def heading_translation(source: str, cache: dict[str, str]) -> str:
    return HEADING_TRANSLATIONS.get(source, english_text(source, cache))


def is_reference_line(text: str) -> bool:
    return any(marker in text for marker in ("网页标题", "课堂用途", "原始链接", "http://", "https://"))


def is_numbered_subheading(body: str, original: str) -> bool:
    if is_reference_line(body) or len(body) > 55:
        return False
    if body.startswith(GOAL_ITEM_PREFIXES):
        return False
    if re.match(r"^\d+[.)、.．]\S", original):
        return len(body) <= 28 or any(word in body for word in ("题目", "展示", "评价", "建议", "算法", "初始化", "坐标", "移动"))
    if original.rstrip().endswith((":", "：")):
        return True
    return any(word in body for word in ("题目", "展示", "评价", "建议", "算法", "初始化", "坐标", "移动"))


def structural_heading(text: str, style: str = "") -> HeadingInfo | None:
    stripped = text.strip()
    if not stripped or is_source_manual_heading(stripped) or is_code_like(stripped):
        return None

    section_heading = normalized_section_heading(stripped)
    if section_heading:
        zh, en = SECTION_HEADINGS[section_heading]
        return HeadingInfo(level=2, zh_text=zh, en_text=en)

    compact = stripped.rstrip(":：").strip()
    if compact in STANDALONE_H2:
        return HeadingInfo(level=2, zh_text=compact, en_source=compact)
    if compact in STANDALONE_H3:
        return HeadingInfo(level=3, zh_text=compact, en_source=compact)

    match = re.match(r"^([一二三四五六七八九十]+)[、.．]\s*(.+)$", compact)
    if match:
        number_text, body = match.groups()
        number = chinese_number_to_int(number_text)
        if number is not None and len(body) <= 55 and not is_reference_line(body):
            level = 2 if body in TOP_LEVEL_NUMBERED_H2 else 3
            return HeadingInfo(level=level, zh_text=f"{number_text}、{body}", en_source=body, en_prefix=f"{number}. ")

    match = re.match(r"^实验([一二三四五六七八九十]+)(（[^）]+）)?[：:]\s*(.+)$", stripped)
    if match:
        number_text, qualifier, body = match.groups()
        number = chinese_number_to_int(number_text)
        if number is not None:
            en_suffix = " (optional extension)" if qualifier and ("拓展" in qualifier or "选做" in qualifier) else ""
            return HeadingInfo(level=3, zh_text=f"实验{number_text}{qualifier or ''}：{body}", en_source=body, en_prefix=f"Experiment {number}{en_suffix}: ")

    match = re.match(r"^实验[：:]\s*(.+)$", stripped)
    if match:
        body = match.group(1).strip()
        return HeadingInfo(level=3, zh_text=f"实验：{body}", en_source=body, en_prefix="Experiment: ")

    match = re.match(r"^题目([一二三四五六七八九十]+)[：:]\s*(.+)$", stripped)
    if match:
        number_text, body = match.groups()
        number = chinese_number_to_int(number_text)
        if number is not None:
            return HeadingInfo(level=3, zh_text=f"题目{number_text}：{body}", en_source=body, en_prefix=f"Task {number}: ")

    match = re.match(r"^阶段(\d+)[：:]\s*(.+)$", stripped)
    if match:
        number, body = match.groups()
        return HeadingInfo(level=3, zh_text=f"阶段{number}：{body}", en_source=body, en_prefix=f"Stage {number}: ")

    match = re.match(r"^(\d+)[.)、.．]\s*(.+)$", compact)
    if match:
        number, body = match.groups()
        if is_numbered_subheading(body, stripped):
            return HeadingInfo(level=3, zh_text=f"{number}. {body}", en_source=body, en_prefix=f"{number}. ")

    if style.lower().startswith("heading"):
        return HeadingInfo(level=3, zh_text=stripped, en_source=stripped)
    return None


def render_heading(heading: HeadingInfo, lang: str, cache: dict[str, str]) -> str:
    if lang == "zh":
        return heading.zh_text
    if heading.en_text is not None:
        return heading.en_text
    source = heading.en_source or heading.zh_text
    return f"{heading.en_prefix}{heading_translation(source, cache)}{heading.en_suffix}".strip()


def bullet_item_text(text: str) -> str | None:
    match = re.match(r"^\s*[*•]\s+(.+)$", text.strip())
    return match.group(1).strip() if match else None


def numbered_item_parts(text: str) -> tuple[int, str] | None:
    match = re.match(r"^\s*(\d+)[.)、.．]\s*(.+)$", text.strip())
    return (int(match.group(1)), match.group(2).strip()) if match else None


def render_paragraph(text: str, style: str, images: tuple[str, ...], lang: str, cache: dict[str, str], image_map: dict[str, str] | None = None) -> str:
    stripped = text.strip()
    blocks: list[str] = []
    if stripped and not is_source_manual_heading(stripped):
        heading = structural_heading(stripped, style)
        if heading:
            rendered = render_heading(heading, lang, cache)
        else:
            rendered = english_text(stripped, cache) if lang == "en" else stripped
        escaped = html.escape(rendered)
        if heading:
            blocks.append(f"<h{heading.level}>{escaped}</h{heading.level}>")
        elif is_code_like(stripped):
            blocks.append(f"<pre><code>{escaped}</code></pre>")
        elif re.match(r"^[0-9]+[.)]\s", stripped):
            blocks.append(f'<p class="step">{escaped}</p>')
        else:
            blocks.append(f"<p>{escaped}</p>")
    for src in images:
        display_src = image_map.get(src, src) if lang == "en" and image_map else src
        alt = english_text(stripped[:80], cache) if lang == "en" else stripped[:80]
        blocks.append(f'<figure><img src="{html.escape(display_src)}" alt="{html.escape(alt or "manual image")}" loading="lazy" decoding="async"></figure>')
    return "\n".join(blocks)


def table_to_rows(table: ET.Element) -> tuple[tuple[str, ...], ...]:
    rows: list[tuple[str, ...]] = []
    for tr in table.findall("./w:tr", NS):
        cells = tuple(text_from(tc) for tc in tr.findall("./w:tc", NS))
        if cells:
            rows.append(cells)
    return tuple(rows)


def render_table(rows: tuple[tuple[str, ...], ...], lang: str, cache: dict[str, str]) -> str:
    rendered_rows = []
    for row in rows:
        cells = []
        for cell in row:
            text = english_text(cell, cache) if lang == "en" else cell
            cells.append(f"<td>{html.escape(text)}</td>")
        rendered_rows.append("<tr>" + "".join(cells) + "</tr>")
    return "" if not rendered_rows else "<table><tbody>\n" + "\n".join(rendered_rows) + "\n</tbody></table>"


def extract_manual(manual: Manual) -> tuple[list[Block], dict[str, int]]:
    source = SOURCE_DIR / manual.source_name
    if not source.exists():
        raise FileNotFoundError(source)
    blocks: list[Block] = []
    stats = {"paragraphs": 0, "tables": 0, "images": 0}
    with zipfile.ZipFile(source) as zf:
        rels = relationship_map(zf)
        root = ET.fromstring(zf.read("word/document.xml"))
        body = root.find("w:body", NS)
        if body is None:
            return blocks, stats
        image_index = 0
        for child in body:
            if child.tag == f"{{{NS['w']}}}p":
                style = paragraph_style(child)
                text = text_from(child, preserve=is_code_style(style))
                images: list[str] = []
                for blip in child.findall(".//a:blip", NS):
                    rid = blip.attrib.get(f"{{{NS['r']}}}embed")
                    if rid:
                        image_index += 1
                        src = copy_image(zf, rels, rid, manual, image_index)
                        if src:
                            images.append(src)
                            stats["images"] += 1
                if text or images:
                    stats["paragraphs"] += 1
                    blocks.append(ParagraphBlock(text, style, tuple(images)))
            elif child.tag == f"{{{NS['w']}}}tbl":
                table = table_to_rows(child)
                if table:
                    stats["tables"] += 1
                    blocks.append(TableBlock(table))
    return blocks, stats


def collect_translation_texts(blocks: list[Block]) -> set[str]:
    texts: set[str] = set()
    for block in blocks:
        if isinstance(block, ParagraphBlock):
            if is_code_block(block):
                continue
            heading = structural_heading(block.text, block.style)
            if heading:
                if heading.en_source and heading.en_source not in HEADING_TRANSLATIONS and should_translate(heading.en_source):
                    texts.add(heading.en_source.strip())
                if block.images and should_translate(block.text[:80]):
                    texts.add(block.text[:80].strip())
                continue
            bullet_text = bullet_item_text(block.text)
            if bullet_text and should_translate(bullet_text):
                texts.add(bullet_text.strip())
                continue
            numbered_item = numbered_item_parts(block.text)
            if numbered_item and not structural_heading(block.text, block.style) and should_translate(numbered_item[1]):
                texts.add(numbered_item[1].strip())
                continue
            if should_translate(block.text):
                texts.add(block.text.strip())
            if block.images and should_translate(block.text[:80]):
                texts.add(block.text[:80].strip())
        else:
            for row in block.rows:
                for cell in row:
                    if should_translate(cell):
                        texts.add(cell.strip())
    return texts


def render_blocks(blocks: list[Block], lang: str, cache: dict[str, str], image_map: dict[str, str] | None = None) -> str:
    rendered: list[str] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        if is_code_block(block):
            code_lines: list[str] = []
            while index < len(blocks) and is_code_candidate(blocks[index]):
                code_lines.append(blocks[index].text.rstrip())  # type: ignore[union-attr]
                index += 1
            while code_lines and not code_lines[0].strip():
                code_lines.pop(0)
            while code_lines and not code_lines[-1].strip():
                code_lines.pop()
            code_text = normalize_code_text(chr(10).join(code_lines))
            rendered.append(f"<pre><code>{html.escape(code_text)}</code></pre>")
            continue
        if isinstance(block, ParagraphBlock) and bullet_item_text(block.text) and not block.images:
            items: list[str] = []
            while index < len(blocks):
                current = blocks[index]
                if not isinstance(current, ParagraphBlock) or current.images:
                    break
                item_text = bullet_item_text(current.text)
                if not item_text:
                    break
                item = english_text(item_text, cache) if lang == "en" else item_text
                items.append(f"<li>{html.escape(item)}</li>")
                index += 1
            rendered.append("<ul>\n" + "\n".join(items) + "\n</ul>")
            continue
        numbered_item = numbered_item_parts(block.text) if isinstance(block, ParagraphBlock) else None
        if isinstance(block, ParagraphBlock) and numbered_item and not block.images and not structural_heading(block.text, block.style):
            items: list[str] = []
            start_number = numbered_item[0]
            while index < len(blocks):
                current = blocks[index]
                if not isinstance(current, ParagraphBlock) or current.images or structural_heading(current.text, current.style):
                    break
                item_parts = numbered_item_parts(current.text)
                if not item_parts:
                    break
                _, item_text = item_parts
                item = english_text(item_text, cache) if lang == "en" else item_text
                items.append(f"<li>{html.escape(item)}</li>")
                index += 1
            rendered.append(f'<ol class="numbered-list" start="{start_number}">\n' + "\n".join(items) + "\n</ol>")
            continue
        if isinstance(block, ParagraphBlock):
            html_block = render_paragraph(block.text, block.style, block.images, lang, cache, image_map)
        else:
            html_block = render_table(block.rows, lang, cache)
        if html_block:
            rendered.append(html_block)
        index += 1
    return "\n".join(rendered)


def manual_label(manual: Manual, lang: str) -> str:
    if manual.slug == FINAL_TEST_SLUG:
        return "\u6bd4\u8d5b\u8bf4\u660e" if lang == "zh" else "Competition"
    return f"\u5b9e\u9a8c {manual.number}" if lang == "zh" else f"Experiment {manual.number}"


def manual_display_title(manual: Manual, lang: str) -> str:
    return manual.zh_title if lang == "zh" else manual.en_title


def nav_html(lang: str, current_slug: str | None = None) -> str:
    home = "\u9996\u9875" if lang == "zh" else "Home"
    items = [f'<li><a class="{"active" if current_slug is None else ""}" href="index.html">{home}</a></li>']
    for manual in MANUALS:
        if manual.slug == FINAL_TEST_SLUG:
            section = "\u6bd4\u8d5b\u8bf4\u660e" if lang == "zh" else "Competition"
            items.append(f'<li class="nav-group">{section}</li>')
        title = manual_display_title(manual, lang)
        label = manual_label(manual, lang)
        active = " active" if current_slug == manual.slug else ""
        items.append(f'<li><a class="{active.strip()}" href="{manual.slug}.html"><span>{label}</span>{html.escape(title)}</a></li>')
    return "\n".join(items)

def layout(lang: str, title: str, body: str, current_slug: str | None = None) -> str:
    zh_href = "index.html" if lang == "zh" else f"../zh/{'index.html' if current_slug is None else current_slug + '.html'}"
    en_href = "index.html" if lang == "en" else f"../en/{'index.html' if current_slug is None else current_slug + '.html'}"
    language_switch = (
        f'<span>\u4e2d\u6587</span><a href="{en_href}">English</a>'
        if lang == "zh"
        else f'<a href="{zh_href}">Chinese</a><span>English</span>'
    )
    project_title = "\u638c\u4e0a\u65e0\u4eba\u673a\u81ea\u4e3b\u7cfb\u7edf\u5b9e\u9a8c\u624b\u518c" if lang == "zh" else "Palm-sized UAV Autonomous Systems Laboratory Manual"
    search = "\u641c\u7d22\u6587\u6863" if lang == "zh" else "Search docs"
    caption = "\u76ee\u5f55" if lang == "zh" else "Contents"
    github = "\u5728 GitHub \u4e0a\u67e5\u770b" if lang == "zh" else "View on GitHub"
    return f"""<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} - {html.escape(project_title)}</title>
  <link rel="icon" type="image/svg+xml" href="../assets/favicon.svg?v=2">
  <link rel="stylesheet" href="../assets/style.css">
</head>
<body>
  <aside class="wy-nav-side">
    <div class="wy-side-scroll">
      <div class="wy-side-nav-search">
        <a class="icon-home" href="index.html">{html.escape(project_title)}</a>
        <div class="version">latest</div>
        <input id="doc-search" type="search" placeholder="{search}" aria-label="{search}">
      </div>
      <nav class="wy-menu">
        <p class="caption">{caption}</p>
        <ul id="nav-list">{nav_html(lang, current_slug)}</ul>
      </nav>
    </div>
  </aside>
  <main class="wy-nav-content-wrap">
    <div class="mobile-bar"><button id="menu-toggle" aria-label="Toggle navigation">&#9776;</button><span>{html.escape(project_title)}</span></div>
    <article class="wy-nav-content">
      <div class="rst-content">
        <div class="breadcrumbs"><a href="index.html">Docs</a><span>&rsaquo;</span><span>{html.escape(title)}</span><a class="github-link" href="https://github.com/Admire-ljb/summer-school-experiment-manual">{github}</a></div>
        <div class="language-switch">{language_switch}</div>
        {body}
      </div>
    </article>
  </main>
  <script src="../assets/site.js"></script>
</body>
</html>
"""


def write_index(lang: str) -> None:
    if lang == "zh":
        body = (
            "<h1>\u638c\u4e0a\u65e0\u4eba\u673a\u5b9e\u9a8c\u624b\u518c</h1>"
            "<p>\u672c\u624b\u518c\u9762\u5411\u638c\u4e0a\u65e0\u4eba\u673a\u5b9e\u9a8c\u8bfe\u7a0b\uff0c\u5185\u5bb9\u5305\u62ec\u73af\u5883\u914d\u7f6e\u3001\u4f20\u611f\u5668\u4f7f\u7528\u3001\u8def\u5f84\u89c4\u5212\u3001cflib \u7f16\u7a0b\u548c\u7efc\u5408\u9879\u76ee\u4efb\u52a1\u3002</p>"
            "<div class=\"admonition warning\"><p class=\"admonition-title\">\u5b89\u5168\u8bf4\u660e</p>"
            "<p>\u6d89\u53ca\u771f\u5b9e\u98de\u884c\u7684\u5b9e\u9a8c\u5fc5\u987b\u5728\u6559\u5e08\u6216\u52a9\u6559\u786e\u8ba4\u573a\u5730\u3001\u8bbe\u5907\u3001\u7535\u6c60\u548c\u6025\u505c\u6d41\u7a0b\u540e\u8fdb\u884c\u3002</p></div>"
            "<div class=\"admonition\"><p class=\"admonition-title\">\u8bfe\u7a0b\u8d44\u6599\u5305</p>"
            "<p>\u8bfe\u7a0b\u8d44\u6599\u5305\u6587\u4ef6\u5939\u540d\u4e3a <code>course-materials</code>\uff0c\u53ef\u901a\u8fc7 <a href=\"https://bhpan.buaa.edu.cn/link/AA5DF49653676B4EDFBAB8B2A09B0FBEE9\">\u5317\u822a\u7f51\u76d8\u94fe\u63a5</a> \u4e0b\u8f7d\uff0c\u6709\u6548\u671f\u81f3 2028-11-11 10:31\u3002\u4e0b\u8f7d\u540e\u8bf7\u89e3\u538b\u4e3a <code>course-materials</code> \u6587\u4ef6\u5939\uff0c\u4ee5\u4fbf\u4e0e\u672c\u6587\u6863\u4e2d\u7684\u8def\u5f84\u4fdd\u6301\u4e00\u81f4\u3002</p></div>"
            "<h2>\u5b9e\u9a8c\u76ee\u5f55</h2><div class=\"toctree-wrapper\">"
        )
        competition_card = ""
        for manual in MANUALS:
            card = f'<a class="doc-card" href="{manual.slug}.html"><span>{manual_label(manual, "zh")}</span><strong>{html.escape(manual_display_title(manual, "zh"))}</strong><em>{html.escape(manual.en_title)}</em></a>\n'
            if manual.slug == FINAL_TEST_SLUG:
                competition_card = card
            else:
                body += card
        body += '</div><h2>\u6bd4\u8d5b\u8bf4\u660e</h2><div class="toctree-wrapper">' + competition_card + '</div>'
        title = "\u638c\u4e0a\u65e0\u4eba\u673a\u5b9e\u9a8c\u624b\u518c"
    else:
        body = "<h1>Palm-sized UAV Autonomous Systems Laboratory Manual</h1><p>This manual covers environment setup, sensor use, path-planning simulation, cflib programming, flight-control routines, and integrated project tasks for palm-sized UAV experiments.</p><div class=\"admonition warning\"><p class=\"admonition-title\">Safety note</p><p>Experiments involving real flight must be conducted only after the instructor or teaching assistant confirms the arena, equipment, batteries, and emergency-stop procedure.</p></div><div class=\"admonition\"><p class=\"admonition-title\">Course Materials Package</p><p>Download the <code>course-materials</code> folder from the <a href=\"https://bhpan.buaa.edu.cn/link/AA5DF49653676B4EDFBAB8B2A09B0FBEE9\">BUAA cloud link</a>. The link is valid until November 11, 2028 at 10:31. After downloading, extract it as <code>course-materials</code> so the paths in this manual match the folder name.</p></div><h2>Experiment list</h2><div class=\"toctree-wrapper\">"
        competition_card = ""
        for manual in MANUALS:
            card = f'<a class="doc-card" href="{manual.slug}.html"><span>{manual_label(manual, "en")}</span><strong>{html.escape(manual_display_title(manual, "en"))}</strong></a>\n'
            if manual.slug == FINAL_TEST_SLUG:
                competition_card = card
            else:
                body += card
        body += '</div><h2>Competition Brief</h2><div class="toctree-wrapper">' + competition_card + '</div>'
        title = "Palm-sized UAV Autonomous Systems Laboratory Manual"
    (ROOT / lang / "index.html").write_text(layout(lang, title, body), encoding="utf-8")

def english_body(manual: Manual, blocks: list[Block], cache: dict[str, str], image_map: dict[str, str]) -> str:
    return f"""
<h1>Experiment {manual.number}: {html.escape(manual.en_title)}</h1>
{render_blocks(blocks, "en", cache, image_map)}
"""


def wall_following_examples(lang: str) -> str:
    if lang == "zh":
        return '''
<div class="admonition"><p class="admonition-title">算法来源与课堂代码</p>
<p>沿墙状态机参考 Bitcraze 官方 <code>crazyflie-demos</code> 仓库。官方示例面向一般直墙环境，默认离墙距离和速度不适用于本课程约 40-50 cm 宽的通道；本手册提供经过窄通道参数调整、测距去抖和运行时限保护的课堂版本。</p>
<ul>
<li>仓库主页：<a href="https://github.com/bitcraze/crazyflie-demos/tree/main">https://github.com/bitcraze/crazyflie-demos/tree/main</a></li>
<li>示例目录：<a href="https://github.com/bitcraze/crazyflie-demos/tree/main/demos/scripts/cflib/multiranger/multiranger_wall_following">demos/scripts/cflib/multiranger/multiranger_wall_following</a></li>
<li><a href="../assets/code/wall_following.py" download>下载课堂控制器：wall_following.py</a></li>
<li><a href="../assets/code/multiranger_wall_following.py" download>下载课堂运行脚本：multiranger_wall_following.py</a></li>
</ul></div>
<p>将两个课堂文件放在虚拟机的同一个 <code>~/workspace</code> 目录中。<code>--wall-side left</code> 表示飞行时墙保持在无人机左侧；如需沿右墙飞行，改为 <code>--wall-side right</code>。</p>
<pre><code>cd ~/workspace
echo "$CFLIB_URI"
python3 multiranger_wall_following.py --wall-side left --max-time 90</code></pre>
<p>课堂参数为：参考离墙距离 <code>0.18 m</code>、前方转向距离 <code>0.24 m</code>、最大前进速度 <code>0.08 m/s</code>、最大侧向修正速度 <code>0.035 m/s</code>。侧面读数必须连续显示为远距离 <code>0.80 s</code> 后才判定墙体结束，以抑制挡板接缝或短暂丢帧造成的误转向。前方小于 <code>0.14 m</code>、任一侧小于 <code>0.09 m</code>、上方小于 <code>0.15 m</code> 或达到最长飞行时间时，脚本停止运动并退出 <code>MotionCommander</code> 以执行降落。</p>
<div class="admonition warning"><p class="admonition-title">首次测试</p><p>先拆除复杂障碍，在低速直墙环境验证左右方向、悬停和上方手势停止；确认无误后再进入窄通道。代码中的阈值以传感器测得距离为准，不等同于机身外缘到墙面的实际净空。</p></div>
'''
    return '''
<div class="admonition"><p class="admonition-title">Algorithm source and classroom scripts</p>
<p>The wall-following state machine is based on Bitcraze's official <code>crazyflie-demos</code> repository. The official demo targets general straight-wall environments; its default wall distance and speed are not suitable for the approximately 40-50 cm-wide course corridors. This manual provides a classroom version with narrow-corridor parameters, range debouncing, and a flight-time limit.</p>
<ul>
<li>Repository: <a href="https://github.com/bitcraze/crazyflie-demos/tree/main">https://github.com/bitcraze/crazyflie-demos/tree/main</a></li>
<li>Demo directory: <a href="https://github.com/bitcraze/crazyflie-demos/tree/main/demos/scripts/cflib/multiranger/multiranger_wall_following">demos/scripts/cflib/multiranger/multiranger_wall_following</a></li>
<li><a href="../assets/code/wall_following.py" download>Download the classroom controller: wall_following.py</a></li>
<li><a href="../assets/code/multiranger_wall_following.py" download>Download the classroom runner: multiranger_wall_following.py</a></li>
</ul></div>
<p>Place both classroom files in the same <code>~/workspace</code> directory. <code>--wall-side left</code> keeps the wall on the aircraft's left; use <code>--wall-side right</code> to follow a right-hand wall.</p>
<pre><code>cd ~/workspace
echo "$CFLIB_URI"
python3 multiranger_wall_following.py --wall-side left --max-time 90</code></pre>
<p>The classroom settings are a <code>0.18 m</code> reference wall distance, <code>0.24 m</code> front turn distance, <code>0.08 m/s</code> maximum forward speed, and <code>0.035 m/s</code> maximum lateral correction. A side reading must remain far for <code>0.80 s</code> before the controller declares the end of a wall, suppressing false turns caused by panel seams or short dropouts. The script stops and leaves <code>MotionCommander</code> to land when the front distance is below <code>0.14 m</code>, either side is below <code>0.09 m</code>, the upper distance is below <code>0.15 m</code>, or the flight-time limit is reached.</p>
<div class="admonition warning"><p class="admonition-title">First test</p><p>Remove complex obstacles first and verify left/right behavior, hover, and the upper-sensor stop gesture beside one straight wall at low speed. The thresholds are sensor ranges and are not the same as the physical clearance from the aircraft frame to the wall.</p></div>
'''


def apply_wall_following_examples(manual: Manual, lang: str, body: str) -> str:
    if "Algorithm source and classroom scripts" in body:
        return body
    if "算法来源与课堂代码" in body:
        return body
    examples = wall_following_examples(lang)
    if lang == "zh":
        marker = "<p>将该节课附上的wall_following.py和multiranger_wall_following.py拷贝至虚拟机中。其中将multiranger_wall_following.py放在workspace目录下，在workspace目录下再新建一个名为wall_following的目录，将wall_following.py文件放入其中，以完成multiranger_wall_following.py文件运行所需要的依赖。</p>"
    else:
        marker = "<p>Copy the wall_following.py and multiranger_wall_following.py attached to this lesson to the virtual machine. Place multiranger_wall_following.py in the workspace directory, create a new directory named wall_following in the workspace directory, and put the wall_following.py file into it to complete the dependencies required to run the multiranger_wall_following.py file.</p>"
    if marker in body:
        return body.replace(marker, examples, 1)
    return body + examples


def cleanup_wall_following_text(manual: Manual, lang: str, body: str) -> str:
    title_pairs = {
        "<h3>实验四（拓展选做）：walk follow the wall</h3>":
        "<h3>实验四（拓展选做）：沿墙飞行</h3>",
        "<h3>实验一：walk follow the wall</h3>":
        "<h3>实验一：沿墙飞行</h3>",
        "<h3>Experiment 4 (optional extension): walk follow the wall</h3>":
        "<h3>Experiment 4 (optional extension): Wall-following flight</h3>",
        "<h3>Experiment 1: walk follow the wall</h3>":
        "<h3>Experiment 1: Wall-following flight</h3>",
    }
    for old, new in title_pairs.items():
        body = body.replace(old, new)

    if manual.slug == "manual-06-complex-map":
        if lang == "zh":
            pattern = r'<p>如下图所示，在multiranger_wall_following\.py文件中的75到77行</p>.*?(?=<h3>实验二：)'
        else:
            pattern = r'<p>As shown in the figure below, lines 75 to 77 in the multiranger_wall_following\.py file</p>.*?(?=<h3>Experiment 2:)'
        body = re.sub(pattern, "", body, count=1, flags=re.DOTALL)
    return body


def replace_code_block_from_asset(
    body: str,
    signatures: tuple[str, ...],
    asset_name: str,
    lang: str,
) -> str:
    code_path = ROOT / "assets" / "code" / asset_name
    code = code_path.read_text(encoding="utf-8")
    replaced = False

    def callback(match: re.Match[str]) -> str:
        nonlocal replaced
        original = html.unescape(match.group(1))
        if replaced or not all(signature in original for signature in signatures):
            return match.group(0)
        replaced = True
        label = "下载经审核的完整脚本" if lang == "zh" else "Download the reviewed script"
        return (
            f'<p><a href="../assets/code/{asset_name}" download>{label}: '
            f'<code>{asset_name}</code></a></p>'
            f'<pre><code>{html.escape(code)}</code></pre>'
        )

    return re.sub(
        r"<pre><code>(.*?)</code></pre>",
        callback,
        body,
        flags=re.DOTALL,
    )


def apply_flight_code_safety_overrides(
    manual: Manual, lang: str, body: str
) -> str:
    replacements = {
        "manual-03-crazyflie-setup": [
            (("Doing a 270deg circle",), "motion_commander_sequence.py"),
        ],
        "manual-04-multiranger": [
            (("multiranger.front:",), "multiranger_read.py"),
            (("allows a user to \"push\"",), "multiranger_push.py"),
        ],
        "manual-05-ranging": [
            (("already,wait a second",), "multiranger_stop.py"),
            (("BOX_LIMIT = 0.3", "def move_box_limit"), "flow_box_bounce.py"),
        ],
        "manual-09-cflib": [
            (("mc.turn_left(180)", "logconf.start()"), "logged_motion_sequence.py"),
            (("BOX_LIMIT = 0.5", "mc.start_forward()"), "flow_box_bounce.py"),
        ],
        "manual-10-motion-commander": [
            (("Doing a 270deg circle",), "motion_commander_sequence.py"),
        ],
        "manual-12-position-commander": [
            (("PositionHlCommander", "pc.go_to(1.0"), "position_hl_square.py"),
        ],
    }
    for signatures, asset_name in replacements.get(manual.slug, []):
        body = replace_code_block_from_asset(body, signatures, asset_name, lang)

    if manual.slug in {"manual-05-ranging", "manual-09-cflib"}:
        body = body.replace("period_in_ms=10", "period_in_ms=100")
    return body


def apply_pointcloud_safety_override(manual: Manual, lang: str, body: str) -> str:
    if manual.slug != "manual-06-complex-map":
        return body
    if lang == "zh":
        title = "官方示例仓库：Multiranger Point Cloud"
        section = '''<div class="admonition"><p class="admonition-title">算法来源与课堂手动建图脚本</p>
<p>点云坐标变换和可视化参考 Bitcraze 官方 <code>multiranger_pointcloud.py</code>。课堂运行使用增加了受控降落、最长飞行时间、日志超时和方向测距保护的版本；官方文件保留为源码参考，不直接作为正式飞行入口。</p>
<ul>
<li>官方示例目录：<a href="https://github.com/bitcraze/crazyflie-demos/tree/main/demos/scripts/cflib/multiranger/multiranger_pointcloud">demos/scripts/cflib/multiranger/multiranger_pointcloud</a></li>
<li><a href="../assets/code/manual_multiranger_pointcloud.py" download>下载课堂脚本：manual_multiranger_pointcloud.py</a></li>
</ul></div>
<p>将课堂脚本放入 <code>~/workspace</code> 后运行：</p>
<pre><code>cd ~/workspace
echo "$CFLIB_URI"
python3 manual_multiranger_pointcloud.py</code></pre>
<p>方向键控制前、后、左、右平移，<code>A</code>/<code>D</code> 控制低速偏航；课堂版固定飞行高度，不再通过按键修改高度。按 <code>Esc</code>、关闭窗口、上方手势停止、日志超时或达到 90 秒上限时，脚本退出 <code>MotionCommander</code> 并降落。某一运动方向小于 <code>0.18 m</code> 时，该方向的平移指令会被抑制。</p>'''
        control_text = "<p>运行后，使用方向键控制前、后、左、右平移，使用 <code>A</code>/<code>D</code> 低速调整航向。飞行高度固定为 <code>0.35 m</code>；松开按键后对应速度立即归零。建图时保持低速，并持续对照现场障碍与点云轮廓。</p>"
    else:
        title = "Official demo repository: Multiranger Point Cloud"
        section = '''<div class="admonition"><p class="admonition-title">Algorithm source and classroom manual-mapping script</p>
<p>The point-cloud transformation and visualization are based on Bitcraze's official <code>multiranger_pointcloud.py</code>. Formal classroom flight uses a version with controlled landing, a flight-time limit, stale-log handling, and direction-aware range guards. The official file remains a source reference and is not the classroom flight entry point.</p>
<ul>
<li>Official demo directory: <a href="https://github.com/bitcraze/crazyflie-demos/tree/main/demos/scripts/cflib/multiranger/multiranger_pointcloud">demos/scripts/cflib/multiranger/multiranger_pointcloud</a></li>
<li><a href="../assets/code/manual_multiranger_pointcloud.py" download>Download the classroom script: manual_multiranger_pointcloud.py</a></li>
</ul></div>
<p>Place the classroom script in <code>~/workspace</code> and run:</p>
<pre><code>cd ~/workspace
echo "$CFLIB_URI"
python3 manual_multiranger_pointcloud.py</code></pre>
<p>The arrow keys command forward, back, left, and right translation; <code>A</code>/<code>D</code> command slow yaw. The classroom version keeps a fixed height. Pressing <code>Escape</code>, closing the window, using the upper-sensor stop gesture, a stale log, or the 90-second limit exits <code>MotionCommander</code> and lands. Translation is suppressed in any commanded direction with less than <code>0.18 m</code> clearance.</p>'''
        control_text = "<p>Use the arrow keys for forward, back, left, and right translation and <code>A</code>/<code>D</code> for slow yaw. The flight height remains fixed at <code>0.35 m</code>, and releasing a key immediately zeros the corresponding velocity. Keep the motion slow and compare the physical obstacles with the point-cloud outline throughout the run.</p>"

    start_pattern = (
        rf'<div class="admonition"><p class="admonition-title">{re.escape(title)}</p>'
        r'.*?(?=<figure><img src="\.\./assets/(?:images|images-en)/manual-06-complex-map/003\.png")'
    )
    body = re.sub(start_pattern, section + "\n", body, count=1, flags=re.DOTALL)
    control_pattern = (
        r'(<figure><img src="\.\./assets/(?:images|images-en)/manual-06-complex-map/003\.png"'
        r' alt="manual image" loading="lazy" decoding="async"></figure>)\s*'
        r'<p>.*?</p>(?=\s*<figure><img src="\.\./assets/(?:images|images-en)/manual-06-complex-map/004\.png")'
    )
    body = re.sub(
        control_pattern,
        lambda match: match.group(1) + "\n" + control_text,
        body,
        count=1,
        flags=re.DOTALL,
    )
    return body

def apply_course_material_overrides(manual: Manual, lang: str, body: str) -> str:
    common_pairs = {
        "<p>本次实验将主要进行python脚本的运行，所有的编程库的调用，皆来自于官方的网址教程：用户指南 |比特热潮</p>":
        "<p>本次实验将主要进行python脚本的运行，编程库参考资料可直接打开 Bitcraze cflib User Guides：</p>\n<pre><code>https://www.bitcraze.io/documentation/repository/crazyflie-lib-python/master/user-guides/</code></pre>",
        "<p>若在进行实验中遇到一些困难，也可点击上述网址进行进一步的参考。同时部分操作和知识要点也在上节课的实验手册中有提及，如有不会的地方可以再参考上节的实验手册，这部分操作这节实验手册不再赘述。</p>":
        "<p>若在进行实验中遇到困难，可直接打开上述网址进一步参考。同时部分操作和知识要点也在上节课的实验手册中有提及，如有不会的地方可以再参考上节的实验手册，这部分操作这节实验手册不再赘述。</p>",
        "<p>This experiment will mainly run python scripts. All programming library calls come from the official website tutorial: User Guide | Bit Boom</p>":
        "<p>This experiment mainly runs Python scripts. Open the Bitcraze cflib User Guides directly:</p>\n<pre><code>https://www.bitcraze.io/documentation/repository/crazyflie-lib-python/master/user-guides/</code></pre>",
        "<p>If you encounter some difficulties during the experiment, you can also click on the above URL for further reference. At the same time, some operations and knowledge points are also mentioned in the experiment manual of the previous class. If you have any questions, you can refer to the experiment manual of the previous section. This part of the operation will not be repeated in this experiment manual.</p>":
        "<p>If you encounter difficulties during the experiment, open the URL listed above for further reference. Some operations and knowledge points are also mentioned in the previous experiment manual; this part is not repeated here.</p>",
        "<p>统一配置：8GB</p>\n\n<p>保留至少8GB内存给物理机。</p>":
        "<p>统一配置：8GB</p>\n<p>保留至少8GB内存给物理机。</p>",
        "<p>Unified configuration: 8GB</p>\n\n<p>Reserve at least 8GB of memory for the host machine.</p>":
        "<p>Unified configuration: 8GB</p>\n<p>Reserve at least 8GB of memory for the host machine.</p>",
        "<p>再下一步让脚本自动帮助我们选择下载速度最快的源，输入数字1按回车键。</p>":
        "<p>再下一步让脚本自动帮助我们选择访问速度最快的软件源，输入数字1按回车键。</p>",
        "<p>The next step is to let the script automatically help us select the source with the fastest download speed. Enter the number 1 and press Enter.</p>":
        "<p>The next step is to let the script automatically help us select the fastest software mirror. Enter the number 1 and press Enter.</p>",
        "<p>再输入以下命令配置一下pip3下载的软件源：</p>":
        "<p>再输入以下命令配置一下pip3使用的软件源：</p>",
        "<p>Then enter the following command to configure the software source downloaded by pip3:</p>":
        "<p>Then enter the following command to configure the software source used by pip3:</p>",
        "<p>课堂用途：用于提高 pip 下载 Python 依赖的速度和稳定性。</p>":
        "<p>课堂用途：用于提高 pip 安装 Python 依赖时的软件源访问速度和稳定性。</p>",
        "<p>Classroom use: Used to improve the speed and stability of pip downloading Python dependencies.</p>":
        "<p>Classroom use: Used to improve the speed and stability of pip access when installing Python dependencies.</p>",
        "<li>手册中的用途是设置 pip index-url，让 cflib、GUI 客户端和相关依赖更快下载。</li>":
        "<li>手册中的用途是设置 pip index-url，让 cflib、GUI 客户端和相关依赖安装时使用清华镜像源。</li>",
        "<li>The purpose in the manual is to set the pip index-url so that cflib, GUI client and related dependencies can be downloaded faster.</li>":
        "<li>The purpose in the manual is to set the pip index-url so that cflib, the GUI client, and related dependencies use the Tsinghua mirror source during installation.</li>",
    }
    manual_pairs: dict[str, dict[str, str]] = {
        "manual-01-vm": {
            "<h3>软件资源（可从官网下载，为节省时间由助教拷贝）</h3>\n<p>VMware Workstation Pro 16</p>\n<p>Ubuntu 20.04 LTS Desktop版镜像文件</p>":
            "<h3>软件资源（从course-materials获取）</h3>\n<p>VMware Workstation Pro 16：<code>course-materials/04_virtual_machine_resources/VMware-workstation-full-16.2.5-20904516.exe</code></p>\n<p>Ubuntu 20.04 LTS Desktop版镜像文件：<code>course-materials/04_virtual_machine_resources/ubuntu-20.04.6-desktop-amd64.iso</code></p>",
            "<h3>Software resources (can be downloaded from the official website, copied by the teaching assistant to save time)</h3>\n<p>VMware Workstation Pro 16</p>\n<p>Ubuntu 20.04 LTS Desktop version image file</p>":
            "<h3>Software resources (from the Course Materials Package)</h3>\n<p>VMware Workstation Pro 16: <code>course-materials/04_virtual_machine_resources/VMware-workstation-full-16.2.5-20904516.exe</code></p>\n<p>Ubuntu 20.04 LTS Desktop image file: <code>course-materials/04_virtual_machine_resources/ubuntu-20.04.6-desktop-amd64.iso</code></p>",
            "<p>具体图文流程在浏览器中打开此链接：</p>":
            "<p>具体图文流程可直接打开以下网址：</p>",
            "<p>For the specific graphic process, open this link in your browser:</p>":
            "<p>For the specific illustrated process, open this URL directly:</p>",
            "<h3>下载与安装</h3>\n<p>访问VMware官网，下载Workstation Pro 16安装包。</p>":
            "<h3>从course-materials安装</h3>\n<p>在course-materials中找到 <code>course-materials/04_virtual_machine_resources/VMware-workstation-full-16.2.5-20904516.exe</code>。</p>",
            "<h3>Download and install</h3>\n<p>Visit the VMware official website and download the Workstation Pro 16 installation package.</p>":
            "<h3>Install from the Course Materials Package</h3>\n<p>In the Course Materials Package, locate <code>course-materials/04_virtual_machine_resources/VMware-workstation-full-16.2.5-20904516.exe</code>.</p>",
            "<p>具体参考图文流程在浏览器中打开此链接：</p>":
            "<p>具体参考图文流程可直接打开以下网址：</p>",
            "<p>Please refer to the graphic process for specific details and open this link in your browser:</p>":
            "<p>For the illustrated reference process, open this URL directly:</p>",
            "<p>该界面中点击浏览选中ubuntu20.04系统映像文件，点击下一步</p>":
            "<p>该界面中点击浏览，选择course-materials中的 <code>course-materials/04_virtual_machine_resources/ubuntu-20.04.6-desktop-amd64.iso</code>，点击下一步</p>",
            "<p>In this interface, click Browse to select the ubuntu20.04 system image file, and click Next</p>":
            "<p>In this interface, click Browse, select <code>course-materials/04_virtual_machine_resources/ubuntu-20.04.6-desktop-amd64.iso</code> from the Course Materials Package, and click Next</p>",
            "<p>在虚拟机设置中，选择CD/DVD驱动器，加载下载的Ubuntu 20.04 ISO文件。</p>":
            "<p>在虚拟机设置中，选择CD/DVD驱动器，加载course-materials中的 <code>course-materials/04_virtual_machine_resources/ubuntu-20.04.6-desktop-amd64.iso</code>。</p>",
            "<p>In the virtual machine settings, select the CD/DVD drive and load the downloaded Ubuntu 20.04 ISO file.</p>":
            "<p>In the virtual machine settings, select the CD/DVD drive and load <code>course-materials/04_virtual_machine_resources/ubuntu-20.04.6-desktop-amd64.iso</code> from the Course Materials Package.</p>",
            "<p>课堂用途：辅助完成 Ubuntu 镜像下载、虚拟机创建、系统安装和国内镜像源配置。</p>":
            "<p>课堂用途：辅助完成 Ubuntu 镜像选择、虚拟机创建、系统安装和国内镜像源配置。</p>",
            "<p>Class purpose: Assist in completing Ubuntu image download, virtual machine creation, system installation and domestic image source configuration.</p>":
            "<p>Class purpose: Assist in selecting the Ubuntu image, creating the virtual machine, installing the system, and configuring domestic mirror sources.</p>",
        },
        "manual-02-ros": {
            "<p>在这里将会一个开源的脚本一键安装配置ROS环境，利用该脚本配置ROS系统将会极为方便，适合初学者快速上手ROS。同时也向同学们推荐一些网络教学视频，学有余力的同学可以对照视频进行ROS学习的巩固和拓展：</p>":
            "<p>这里使用course-materials中的 FishROS 一键安装脚本配置 ROS 环境。脚本位置为 <code>course-materials/02_scripts_and_code/04_fishros_install.sh</code>。利用该脚本配置ROS系统将会极为方便，适合初学者快速上手ROS。同时也向同学们推荐一些网络教学视频，学有余力的同学可以对照视频进行ROS学习的巩固和拓展：</p>",
            "<p>Here we will use an open source script to install and configure the ROS environment with one click. Using this script to configure the ROS system will be extremely convenient and suitable for beginners to quickly get started with ROS. At the same time, we also recommend some online teaching videos to students. Students who are willing to learn can refer to the videos to consolidate and expand their ROS learning:</p>":
            "<p>Here we use the FishROS one-click installation script from the Course Materials Package to configure the ROS environment. The script is located at <code>course-materials/02_scripts_and_code/04_fishros_install.sh</code>. Using this script to configure the ROS system is convenient for beginners. At the same time, we also recommend some online teaching videos to students. Students who are willing to learn can refer to the videos to consolidate and expand their ROS learning:</p>",
            "<p>打开虚拟机，进入主界面后呼出终端（鼠标点击一下桌面后，同时按住ctrl+alt+T键，参考第一节课的实验手册。）</p>\n<p>在终端中输入如下命令(可以右键选中如下命令点击复制，再粘贴到终端中)：</p>\n<p>wget http://fishros.com/install -O fishros &amp;&amp; . fishros</p>":
            "<p>先将 <code>course-materials/02_scripts_and_code/04_fishros_install.sh</code> 拖入虚拟机的用户目录或 <code>workspace</code> 文件夹中。打开虚拟机，进入主界面后呼出终端（鼠标点击一下桌面后，同时按住ctrl+alt+T键，参考第一节课的实验手册。）</p>\n<p>在脚本所在目录中输入如下命令运行脚本：</p>\n<pre><code>cp 04_fishros_install.sh fishros\n. fishros</code></pre>\n<p>该脚本本身已经放在course-materials中，但安装 ROS 和系统依赖时仍需要虚拟机联网。</p>",
            "<p>Open the virtual machine, enter the main interface and call out the terminal (after clicking the mouse on the desktop, press and hold the ctrl+alt+T keys at the same time, refer to the experiment manual of the first lesson.)</p>\n<p>Enter the following command in the terminal (you can right-click to select the following command, click copy, and then paste it into the terminal):</p>\n<p>wget http://fishros.com/install -O fishros &amp;&amp; . fishros</p>":
            "<p>First drag <code>course-materials/02_scripts_and_code/04_fishros_install.sh</code> into the virtual machine user directory or the <code>workspace</code> folder. Open the virtual machine, enter the main interface and call out the terminal (after clicking the mouse on the desktop, press and hold the ctrl+alt+T keys at the same time, refer to the experiment manual of the first lesson.)</p>\n<p>In the directory containing the script, enter the following commands to run it:</p>\n<pre><code>cp 04_fishros_install.sh fishros\n. fishros</code></pre>\n<p>The script file is included in the Course Materials Package, but installing ROS and system dependencies still requires network access inside the virtual machine.</p>",
            "<p>课堂用途：用于通过命令行下载并运行 ROS 安装脚本。</p>\n<ul>\n<li>手册中的命令为：wget http://fishros.com/install -O fishros &amp;&amp; . fishros</li>":
            "<p>课堂用途：用于从course-materials运行 ROS 安装脚本。</p>\n<ul>\n<li>course-materials位置：<code>course-materials/02_scripts_and_code/04_fishros_install.sh</code></li>\n<li>手册中的运行命令为：<code>cp 04_fishros_install.sh fishros</code>，然后执行 <code>. fishros</code></li>",
            "<p>Classroom use: Used to download and run the ROS installation script through the command line.</p>\n<ul>\n<li>The command in the manual is: wget http://fishros.com/install -O fishros &amp;&amp; . fishros</li>":
            "<p>Classroom use: Used to run the ROS installation script from the Course Materials Package.</p>\n<ul>\n<li>Course Materials Package location: <code>course-materials/02_scripts_and_code/04_fishros_install.sh</code></li>\n<li>Run it with: <code>cp 04_fishros_install.sh fishros</code>, then <code>. fishros</code></li>",
        },
        "manual-03-crazyflie-setup": {
            "<p>直接用图形化操作的方法，在主机windows的文件界面将软件包拖动进linux虚拟机的文件界面即可。</p>":
            """<p>本节使用 Git 安装 cfclient，并固定到 Bitcraze 官方仓库中兼容 Ubuntu 20.04 默认 Python 3.8 的 <code>2024.7.1</code> 版本。<code>2024.10</code> 及后续版本要求 Python 3.10，不适用于本课程的默认虚拟机环境。打开虚拟机终端，先进入 <code>workspace</code> 并获取源码：</p>
<pre><code>mkdir -p ~/workspace
cd ~/workspace
git clone https://github.com/bitcraze/crazyflie-clients-python.git
cd crazyflie-clients-python
git checkout 2024.7.1</code></pre>""",
            "<p>Directly use the graphical operation method to drag the software package into the file interface of the Linux virtual machine from the file interface of the host windows.</p>":
            """<p>Install cfclient with Git and use Bitcraze release <code>2024.7.1</code>, the last official release compatible with the Python 3.8 provided by Ubuntu 20.04. Releases <code>2024.10</code> and later require Python 3.10 and are not compatible with the course virtual machine. Open a terminal in the virtual machine, enter <code>workspace</code>, and get the source code:</p>
<pre><code>mkdir -p ~/workspace
cd ~/workspace
git clone https://github.com/bitcraze/crazyflie-clients-python.git
cd crazyflie-clients-python
git checkout 2024.7.1</code></pre>""",
            "<p>再双击该压缩包，点击extract解压至该文件目录下。</p>":
            "<p>如果已经克隆过该仓库，不需要重新下载；进入已有目录后执行 <code>git fetch --tags</code>，再执行 <code>git checkout 2024.7.1</code>。确认当前终端目录为 <code>~/workspace/crazyflie-clients-python</code>，后续依赖安装和 <code>cfclient</code> 安装命令均在该目录中执行。</p>",
            "<p>Double-click the compressed package and click extract to extract it to the file directory.</p>":
            "<p>If the repository has already been cloned, do not download it again. Enter the existing directory, run <code>git fetch --tags</code>, and then run <code>git checkout 2024.7.1</code>. Confirm that the current terminal directory is <code>~/workspace/crazyflie-clients-python</code>; run the dependency and <code>cfclient</code> installation commands from this directory.</p>",
            "<p>具体的无人机基础认知教程可参考该官方网址：Getting started with the Crazyflie 2.0 or Crazyflie 2.1(+) | Bitcraze</p>":
            "<p>具体的无人机基础认知教程可直接打开 Bitcraze 官方教程：</p>\n<pre><code>https://www.bitcraze.io/documentation/tutorials/getting-started-with-crazyflie-2-x/</code></pre>",
            "<p>For specific basic drone cognition tutorials, please refer to this official website: Getting started with the Crazyflie 2.0 or Crazyflie 2.1(+) | Bitcraze</p>":
            "<p>For the basic Crazyflie tutorial, open the official Bitcraze tutorial directly:</p>\n<pre><code>https://www.bitcraze.io/documentation/tutorials/getting-started-with-crazyflie-2-x/</code></pre>",
            "<p>首先先配置linux虚拟机中的usb设备的权限，详细的操作可以再参考官方网址的教程：</p>\n<p>USB permissions | Bitcraze</p>":
            "<p>首先先配置linux虚拟机中的usb设备的权限，详细操作可直接打开 Bitcraze USB permissions 页面：</p>\n<pre><code>https://www.bitcraze.io/documentation/repository/crazyflie-lib-python/master/installation/usb_permissions/</code></pre>",
            "<p>First, configure the permissions of the USB device in the Linux virtual machine. For detailed operations, you can refer to the tutorial on the official website:</p>\n<p>USB permissions | Bitcraze</p>":
            "<p>First, configure the permissions of the USB device in the Linux virtual machine. For detailed operations, open the Bitcraze USB permissions page directly:</p>\n<pre><code>https://www.bitcraze.io/documentation/repository/crazyflie-lib-python/master/installation/usb_permissions/</code></pre>",
            "<p>补充，实验官方教程网址为：https://www.bitcraze.io/documentation/tutorials/getting-started-with-stem-drone-bundle/</p>":
            "<p>补充，实验官方教程网址为：</p>\n<pre><code>https://www.bitcraze.io/documentation/tutorials/getting-started-with-stem-drone-bundle/</code></pre>",
            "<p>Supplement, the official tutorial website for the experiment is: https://www.bitcraze.io/documentation/tutorials/getting-started-with-stem-drone-bundle/</p>":
            "<p>Supplement: open the official experiment tutorial directly:</p>\n<pre><code>https://www.bitcraze.io/documentation/tutorials/getting-started-with-stem-drone-bundle/</code></pre>",
        },
        "manual-04-multiranger": {
            "<p>该模块的官方教程网址：Multi-ranger deck | Bitcraze</p>":
            "<p>该模块的产品说明可直接打开 Bitcraze 页面：</p>\n<pre><code>https://store.bitcraze.io/products/multi-ranger-deck</code></pre>",
            "<p>The official tutorial URL of this module: Multi-ranger deck | Bitcraze</p>":
            "<p>Open the Bitcraze product page for this module directly:</p>\n<pre><code>https://store.bitcraze.io/products/multi-ranger-deck</code></pre>",
        },
        "manual-06-complex-map": {
            "<p>将本节课附带的multiranger_pointcloud.py文件放入workspace中，该python脚本可直接运行。如下图所示，该程序的主要功能为crazyflie无人机在障碍环境中使用multiranger模块进行周边障碍物的点云地图建图。</p>":
            "<div class=\"admonition\"><p class=\"admonition-title\">官方示例仓库：Multiranger Point Cloud</p><p><code>multiranger_pointcloud.py</code> 来源于 Bitcraze 官方 <code>crazyflie-demos</code> 仓库。课堂以官方仓库中的文件为准，手册列出来源和使用方式。</p><ul><li>仓库主页：<a href=\"https://github.com/bitcraze/crazyflie-demos/tree/main\">https://github.com/bitcraze/crazyflie-demos/tree/main</a></li><li>示例目录：<a href=\"https://github.com/bitcraze/crazyflie-demos/tree/main/demos/scripts/cflib/multiranger/multiranger_pointcloud\">demos/scripts/cflib/multiranger/multiranger_pointcloud</a></li><li><code>multiranger_pointcloud.py</code>：<a href=\"https://github.com/bitcraze/crazyflie-demos/blob/main/demos/scripts/cflib/multiranger/multiranger_pointcloud/multiranger_pointcloud.py\">官方文件链接</a></li></ul></div><p>建议在虚拟机中按以下方式使用：</p><pre><code>cd ~/workspace\ngit clone https://github.com/bitcraze/crazyflie-demos.git\ncd crazyflie-demos/demos/scripts/cflib/multiranger/multiranger_pointcloud\npython3 multiranger_pointcloud.py</code></pre><p>运行前请确认 Crazyflie、Crazyradio、Flow deck 和 Multi-ranger deck 已连接正常；该示例需要图形界面和 Python 可视化依赖，若提示缺少依赖，请根据官方 README 安装 <code>numpy</code>、<code>vispy</code> 和 <code>PyQt6</code>。首次运行应在安全场地中进行，并确认窗口关闭后无人机会正常降落。</p>",
            "<p>Put the multiranger_pointcloud.py file attached to this lesson into the workspace, and the python script can be run directly. As shown in the figure below, the main function of this program is to use the multiranger module of the crazyflie drone in an obstacle environment to construct point cloud maps of surrounding obstacles.</p>":
            "<div class=\"admonition\"><p class=\"admonition-title\">Official demo repository: Multiranger Point Cloud</p><p><code>multiranger_pointcloud.py</code> comes from Bitcraze's official <code>crazyflie-demos</code> repository. Use the file in the official repository as the source of record; this manual lists the source link and classroom usage steps.</p><ul><li>Repository: <a href=\"https://github.com/bitcraze/crazyflie-demos/tree/main\">https://github.com/bitcraze/crazyflie-demos/tree/main</a></li><li>Demo directory: <a href=\"https://github.com/bitcraze/crazyflie-demos/tree/main/demos/scripts/cflib/multiranger/multiranger_pointcloud\">demos/scripts/cflib/multiranger/multiranger_pointcloud</a></li><li><code>multiranger_pointcloud.py</code>: <a href=\"https://github.com/bitcraze/crazyflie-demos/blob/main/demos/scripts/cflib/multiranger/multiranger_pointcloud/multiranger_pointcloud.py\">official file link</a></li></ul></div><p>Recommended usage in the virtual machine:</p><pre><code>cd ~/workspace\ngit clone https://github.com/bitcraze/crazyflie-demos.git\ncd crazyflie-demos/demos/scripts/cflib/multiranger/multiranger_pointcloud\npython3 multiranger_pointcloud.py</code></pre><p>Before running the demo, confirm that the Crazyflie, Crazyradio, Flow deck, and Multi-ranger deck are connected correctly. This example requires a graphical desktop and Python visualization dependencies; if dependencies are missing, install <code>numpy</code>, <code>vispy</code>, and <code>PyQt6</code> according to the official README. Run the first test in a safe area and confirm that the drone lands normally after the visualization window is closed.</p>",
        },
        "manual-08-path-planning": {
            "<p>同时再打开本机上存放今天实验所需要的工程文件压缩包的所在位置（该压缩包放在电脑桌面或者某个文件夹都可以）。鼠标选中本机上的压缩包文件，直接拖动到虚拟机中的workspace中。</p>":
            "<p>同时打开course-materials中的项目压缩文件位置：<code>course-materials/00_project_archives/uav_motion_planning.zip</code>。鼠标选中该压缩包文件，直接拖动到虚拟机中的workspace中。</p>",
            "<p>At the same time, open the location on the local computer where the compressed package of project files required for today&#x27;s experiment is stored (the compressed package can be placed on the computer desktop or in a certain folder). Select the compressed package file on the local machine with the mouse and drag it directly to the workspace in the virtual machine.</p>":
            "<p>At the same time, open the project archive in the Course Materials Package: <code>course-materials/00_project_archives/uav_motion_planning.zip</code>. Select this archive on the host machine and drag it directly into <code>workspace</code> in the virtual machine.</p>",
            "<p>接下来输入以下命令（可能会因为无法连接到外网而失败，可以多试几次）:</p>":
            "<p>接下来输入以下命令（如虚拟机缺少系统依赖或软件源不可用，可能需要先检查网络或离线源配置）:</p>",
            "<p>Next enter the following command (it may fail because you cannot connect to the external network, you can try a few more times):</p>":
            "<p>Next enter the following command (if system dependencies are missing or the software source is unavailable, check the network or offline-source configuration first):</p>",
        },
        "manual-09-cflib": {
            "<p>可以看到，我们在第10行导入了cflib中的motioncommander模块，我们将调用该模块的功能使得无人机进行飞行，详细的类函数，有余力的同学可以进入该网址查看：github.com</p>":
            "<p>可以看到，我们在第10行导入了cflib中的motioncommander模块，我们将调用该模块的功能使得无人机进行飞行。详细的类函数可查看course-materials中的源码：<code>course-materials/05_source_references/crazyflie-lib-python-master.zip</code>。</p>",
            "<p>As you can see, we imported the motioncommander module in cflib on line 10. We will call the function of this module to make the drone fly. For detailed class functions, students who have spare capacity can go to this website to view: github.com</p>":
            "<p>As you can see, we imported the motioncommander module in cflib on line 10. We will call this module to fly the drone. For detailed class functions, refer to the source archive in the Course Materials Package: <code>course-materials/05_source_references/crazyflie-lib-python-master.zip</code>.</p>",
        },
    }
    for old, new in common_pairs.items():
        body = body.replace(old, new)
    for old, new in manual_pairs.get(manual.slug, {}).items():
        body = body.replace(old, new)
    if manual.slug in {"manual-05-ranging", "manual-06-complex-map"}:
        body = apply_wall_following_examples(manual, lang, body)
        body = cleanup_wall_following_text(manual, lang, body)
    body = apply_pointcloud_safety_override(manual, lang, body)
    return body


def vm_manual_supplement(lang: str) -> str:
    if lang == "zh":
        return '''<h3>Mac 用户补充方案</h3>
<p>Intel Mac 用户可以继续使用本实验主流程中的 amd64 Ubuntu 20.04 Desktop 镜像，只需将虚拟机软件替换为 VMware Fusion、UTM 或 VirtualBox 等 macOS 可用工具。</p>
<p>Apple Silicon Mac（M1/M2/M3/M4）不能直接使用 amd64 桌面镜像，应使用 ARM64 Ubuntu 虚拟机。ARM64 镜像地址：</p>
<pre><code>https://cdimage.ubuntu.com/ubuntu/releases/20.04.5/release/ubuntu-20.04.5-live-server-arm64.iso</code></pre>
<p>该镜像是 Ubuntu Server，默认没有图形界面。使用 VMware Fusion 创建虚拟机并启动后，按文本安装界面完成以下配置：语言选择 English，键盘保持 English (US)，网络使用 DHCP，镜像源保持默认，磁盘选择 <code>Use an entire disk</code>，创建用户名、主机名和密码；OpenSSH 可按需要勾选，其他附加软件包暂不选择。安装完成后选择 <code>Reboot Now</code>，如提示移除安装介质，请在虚拟机设置中断开 ISO 后回车继续。</p>
<p>首次登录命令行后，执行以下命令安装桌面环境和 VMware 工具：</p>
<pre><code>sudo apt update
sudo apt install -y ubuntu-desktop open-vm-tools open-vm-tools-desktop
sudo reboot</code></pre>
<div class="admonition warning"><p class="admonition-title">课堂建议</p><p>Apple Silicon 方案应作为补充方案使用，并在正式实验前完成 ROS Noetic、cfclient、课程仿真工程和 Crazyradio USB 透传测试。课堂主方案仍建议使用 x86_64 Ubuntu 20.04 Desktop 虚拟机，以保证环境一致。</p></div>
'''
    return '''<h3>Supplement for Mac Users</h3>
<p>Intel Mac users can continue to use the amd64 Ubuntu 20.04 Desktop image in the main workflow. Replace VMware Workstation with a macOS virtualization tool such as VMware Fusion, UTM, or VirtualBox.</p>
<p>Apple Silicon Macs (M1/M2/M3/M4) should not use the amd64 desktop image directly. Use an ARM64 Ubuntu virtual machine instead. ARM64 image URL:</p>
<pre><code>https://cdimage.ubuntu.com/ubuntu/releases/20.04.5/release/ubuntu-20.04.5-live-server-arm64.iso</code></pre>
<p>This image is Ubuntu Server and does not include a desktop environment by default. After creating and starting the virtual machine in VMware Fusion, complete the text-mode installer as follows: select English, keep the keyboard as English (US), use DHCP networking, keep the default mirror, select <code>Use an entire disk</code>, and create the username, host name, and password. OpenSSH is optional; leave other extra package selections empty. After installation, choose <code>Reboot Now</code>. If the installer asks you to remove the installation medium, disconnect the ISO in the virtual-machine settings and press Enter.</p>
<p>After the first command-line login, install the desktop environment and VMware tools:</p>
<pre><code>sudo apt update
sudo apt install -y ubuntu-desktop open-vm-tools open-vm-tools-desktop
sudo reboot</code></pre>
<div class="admonition warning"><p class="admonition-title">Classroom note</p><p>Treat the Apple Silicon path as a supplemental path and verify ROS Noetic, cfclient, the course simulation project, and Crazyradio USB passthrough before the formal lab. The primary classroom path should remain an x86_64 Ubuntu 20.04 Desktop VM so that the environment stays consistent.</p></div>
'''


def apply_vm_manual_overrides(lang: str, body: str) -> str:
    if lang == "zh":
        marker = '<h2>三、实验步骤</h2>'
        sentinel = "Mac 用户补充方案"
        replacements = {
            "<p>物理机配置：建议8GB以上内存、50GB以上可用磁盘空间（虚拟机需占用约20GB）。</p>":
            "<p>物理机配置：建议16GB以上内存，并在安装前预留约40GB以上可用磁盘空间。虚拟机推荐配置为8GB内存、最大60GB可增长虚拟磁盘；不要勾选“立即分配所有磁盘空间”，宿主机只会按虚拟机实际写入量逐步占用空间。若宿主机磁盘空间确实不足，可将虚拟磁盘最大容量设置为20-30GB，并优先选择30GB和Ubuntu最小安装。课程期间应留意宿主机剩余空间，并只保留必要的初始快照和当前快照。</p>",
            "<p>运行内存可以使用默认推荐内存，点击下一步</p>":
            "<p>运行内存设置为8GB，设置完成后点击下一步</p>",
            "<p>可以稍微增大磁盘空间，点击下一步</p>":
            "<p>推荐将磁盘最大容量设置为60GB，不勾选“立即分配所有磁盘空间”，保持“将虚拟磁盘拆分成多个文件”即可。虚拟磁盘会按实际使用量增长，不会在创建时立即占用60GB；下图中的30GB用于展示设置位置。若宿主机空间确实不足，可设置为20-30GB，建议尽量选择30GB，并在课程期间避免安装无关软件和保留过多快照。设置完成后点击下一步。</p>",
            "<p>处理器：根据物理机核心数分配（如4核CPU分配2核，每个核心1-2线程）。</p>":
            "<p>处理器：根据物理机核心数分配，建议至少分配4个虚拟CPU；高性能电脑可分配6-8个虚拟CPU，但应保留足够资源给宿主机。</p>",
            "<p>基础任务：2GB</p>":
            "<p>统一配置：8GB</p>",
            "<p>多任务/开发环境：4GB</p>":
            "",
            "<p>保留至少4GB内存给物理机。</p>":
            "<p>保留至少8GB内存给物理机。</p>",
            "<p>容量：分配60GB，选择“存储为单个文件”。</p>":
            "<p>容量：推荐最大60GB；宿主机空间确实不足时可设置为20-30GB，并优先选择30GB。不立即分配全部空间，保持“将虚拟磁盘拆分成多个文件”即可。</p>",
            "<p>/（根目录）：20GB，EXT4文件系统。</p>":
            "<p>/（根目录）：40GB，EXT4文件系统。</p>",
            "<p>Swap（交换分区）：2GB（内存不足时备用）。</p>":
            "<p>Swap（交换分区）：4GB（内存不足时备用）。</p><p>上述分区方案适用于推荐的60GB虚拟磁盘。若采用20-30GB空间受限配置，请选择Ubuntu“清除整个磁盘并安装Ubuntu”进行虚拟磁盘自动分区，并选择最小安装；该操作仅作用于当前虚拟机的虚拟磁盘。不要在20-30GB虚拟磁盘上套用40GB根分区方案。</p>",
        }
    else:
        marker = '<h2>3. Experimental steps</h2>'
        sentinel = "Supplement for Mac Users"
        replacements = {
            "<p>Physical machine configuration: It is recommended to have more than 8GB of memory and more than 50GB of available disk space (the virtual machine needs to occupy about 20GB).</p>":
            "<p>Physical machine configuration: more than 16GB of memory and about 40GB or more of available host storage before installation are recommended. The recommended virtual-machine configuration is 8GB of memory and a growable virtual disk with a 60GB maximum. Do not select &quot;Allocate all disk space now&quot;; host storage is consumed gradually as data is written to the virtual machine. If host storage is genuinely limited, set the virtual-disk maximum to 20-30GB, preferably 30GB, and use Ubuntu Minimal Installation. Monitor free host storage during the course and retain only the necessary clean and current snapshots.</p>",
            "<p>You can use the default recommended memory for running memory, click Next</p>":
            "<p>Set the virtual-machine memory to 8GB, then click Next.</p>",
            "<p>You can slightly increase the disk space, click Next</p>":
            "<p>Set the recommended maximum disk capacity to 60GB, do not select &quot;Allocate all disk space now&quot;, and keep &quot;Split virtual disk into multiple files&quot;. The disk grows with actual use and does not immediately occupy 60GB. The 30GB value in the following image indicates where the setting is located. If host storage is genuinely limited, use 20-30GB, preferably 30GB, and avoid installing unrelated software or retaining excessive snapshots during the course. Then click Next.</p>",
            "<p>Processor: allocated according to the number of cores of the physical machine (for example, a 4-core CPU is allocated 2 cores, and each core has 1-2 threads).</p>":
            "<p>Processor: allocate resources according to the number of host CPU cores. At least 4 virtual CPUs are recommended. High-performance computers may use 6-8 virtual CPUs, while keeping enough resources for the host system.</p>",
            "<p>Basic tasks: 2GB</p>":
            "<p>Unified configuration: 8GB</p>",
            "<p>Multitasking/development environment: 4GB</p>":
            "",
            "<p>Reserve at least 4GB of memory for the physical machine.</p>":
            "<p>Reserve at least 8GB of memory for the host machine.</p>",
            "<p>Capacity: Allocate 60GB, select &quot;Store as single file&quot;.</p>":
            "<p>Capacity: a 60GB maximum is recommended. If host storage is genuinely limited, use 20-30GB, preferably 30GB. Do not allocate all space immediately, and keep &quot;Split virtual disk into multiple files&quot;.</p>",
            "<p>/ (root directory): 20GB, EXT4 file system.</p>":
            "<p>/ (root directory): 40GB, EXT4 file system.</p>",
            "<p>Swap (swap partition): 2GB (spare when memory is insufficient).</p>":
            "<p>Swap (swap partition): 4GB (spare when memory is insufficient).</p><p>The partitioning scheme above applies to the recommended 60GB virtual disk. For a storage-constrained 20-30GB configuration, select Ubuntu's &quot;Erase disk and install Ubuntu&quot; option to partition the virtual disk automatically and use Minimal Installation. This operation affects only the current virtual machine's virtual disk. Do not apply the 40GB root-partition scheme to a 20-30GB virtual disk.</p>",
        }
    for old, new in replacements.items():
        body = body.replace(old, new)
    if sentinel not in body and marker in body:
        body = body.replace(marker, vm_manual_supplement(lang) + marker, 1)
    return body


def apply_cflib_copyable_code_overrides(lang: str, body: str) -> str:
    takeoff_program = """import logging
import sys
import time
from threading import Event

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.positioning.motion_commander import MotionCommander
from cflib.utils import uri_helper

URI = uri_helper.uri_from_env(default='')
DEFAULT_HEIGHT = 0.35
deck_attached_event = Event()

logging.basicConfig(level=logging.ERROR)


def param_deck_flow(_, value_str):
    value = int(value_str)
    print(value)
    if value:
        deck_attached_event.set()
        print('Deck is attached!')
    else:
        print('Deck is NOT attached!')


def request_arming(scf, armed):
    for service_name in ('platform', 'supervisor'):
        service = getattr(scf.cf, service_name, None)
        request = getattr(service, 'send_arming_request', None)
        if request is not None:
            request(armed)
            return
    raise RuntimeError('This cflib version has no arming service.')


def take_off_simple(scf):
    with MotionCommander(scf, default_height=DEFAULT_HEIGHT) as mc:
        time.sleep(3)
        mc.stop()


if __name__ == '__main__':
    cflib.crtp.init_drivers()
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache='./cache')) as scf:
        scf.cf.param.add_update_callback(
            group='deck',
            name='bcFlow2',
            cb=param_deck_flow,
        )
        time.sleep(1)

        if not deck_attached_event.wait(timeout=5):
            print('No flow deck detected!')
            sys.exit(1)

        armed = False
        try:
            request_arming(scf, True)
            armed = True
            time.sleep(1.0)
            take_off_simple(scf)
        finally:
            if armed:
                request_arming(scf, False)"""
    forward_back_function = """def move_linear_simple(scf):
    with MotionCommander(scf, default_height=DEFAULT_HEIGHT) as mc:
        time.sleep(1)
        mc.forward(0.5)
        time.sleep(1)
        mc.back(0.5)
        time.sleep(1)"""
    turn_function = """def move_linear_simple(scf):
    with MotionCommander(scf, default_height=DEFAULT_HEIGHT) as mc:
        time.sleep(1)
        mc.forward(0.5)
        time.sleep(1)
        mc.turn_left(180)
        time.sleep(1)
        mc.forward(0.5)
        time.sleep(1)"""

    code_blocks = {
        6: f"<pre><code>{html.escape(takeoff_program)}</code></pre>",
        7: f"<pre><code>{html.escape(forward_back_function)}</code></pre>",
        8: f"<pre><code>{html.escape(turn_function)}</code></pre>",
    }
    for index in (2, 4, 5, 9):
        pattern = rf'<figure><img src="\.\./assets/(?:images|images-en)/manual-09-cflib/{index:03d}\.png" alt="manual image" loading="lazy" decoding="async"></figure>'
        body = re.sub(pattern, "", body)
    for index, replacement in code_blocks.items():
        pattern = rf'<figure><img src="\.\./assets/(?:images|images-en)/manual-09-cflib/{index:03d}\.png" alt="manual image" loading="lazy" decoding="async"></figure>'
        body = re.sub(pattern, replacement, body)

    if lang == "zh":
        paragraph_replacements = {
            "<p>将已有的程序按照如下图所示的程序进行编写。（之前的param_deck_flow函数可以保留），然后运行该程序，无人机将会起飞悬停3秒后降落。第21至23行则会控制该飞行流程，第14行设置了默认起飞高度。可以适当改变这些参数来观察效果。</p>":
            "<p>将 <code>motion_flying.py</code> 改为下面的完整可复制版本。运行后，无人机将起飞并悬停 3 秒，然后自动降落。<code>DEFAULT_HEIGHT</code> 设置默认起飞高度；首次测试时应保持低高度，并确认急停方式。</p>",
            "<p>我们再在主函数前添加以下函数，将程序最后一行要调用的函数替换为该函数。（例如将刚才在上图42行调用的take_off_simple函数替换为现在的move_linear_simple函数）。该函数的作用为无人机起飞之后，悬停一秒，前进0.5米，再悬停一秒，后退0.5米，再悬停一秒，随后降落。我们通过motioncommander类实体化一个对象mc，通过调用mc的成员函数forward和back实现无人机的前进后退。</p>":
            "<p>在主函数前添加下面的 <code>move_linear_simple</code> 函数，并将主函数最后调用的 <code>take_off_simple(scf)</code> 改为 <code>move_linear_simple(scf)</code>。无人机起飞后将悬停 1 秒、前进 0.5 米、再次悬停 1 秒、后退 0.5 米，随后降落。</p>",
            "<p>再进一步地，我们将函数的内容替换为如下：</p>":
            "<p>如果需要演示转向后返回，将 <code>move_linear_simple</code> 替换为下面的可复制版本：</p>",
            "<p>根据我们学习到的在终端中打印出无人机在实时运行时的飞行数据，参照如下代码（take_off_simple(scf)函数和param_deck_flow(name, value_str)函数可以保留，也可以如下所示无内容）：</p>":
            "<p>下面给出记录实时位置数据的完整可复制程序。其中 <code>log_pos_callback</code> 更新位置估计，<code>param_deck_flow</code> 检查 Flow deck 是否已连接。</p>",
            "<p>再新定义加入一个名字为move_box_limit的函数，放在主函数中，同样地参考程序如下：</p>":
            "<p>下面给出包含 <code>move_box_limit</code> 的完整可复制程序。运行前请确认位置日志能够正常更新，并由一名组员负责急停。</p>",
        }
    else:
        paragraph_replacements = {
            "<p>Write the existing program as shown in the figure below. (The previous param_deck_flow function can be retained), then run the program, the drone will take off and hover for 3 seconds before landing. Lines 21 to 23 will control the flight process, and line 14 sets the default takeoff altitude. These parameters can be changed appropriately to observe the effect.</p>":
            "<p>Replace <code>motion_flying.py</code> with the complete copyable version below. The drone takes off, hovers for 3 seconds, and then lands automatically. <code>DEFAULT_HEIGHT</code> sets the default takeoff height; keep it low for the first test and confirm the emergency-stop procedure.</p>",
            "<p>We then add the following function before the main function and replace the function to be called in the last line of the program with this function. (For example, replace the take_off_simple function just called in line 42 of the figure above with the current move_linear_simple function). The function of this function is that after the drone takes off, it hovers for one second, moves forward 0.5 meters, hovers for another second, retreats 0.5 meters, hovers for another second, and then lands. We materialize an object mc through the motioncommander class, and realize the forward and backward movement of the drone by calling the member functions forward and back of mc.</p>":
            "<p>Add the copyable <code>move_linear_simple</code> function below before the main function, and replace the final <code>take_off_simple(scf)</code> call with <code>move_linear_simple(scf)</code>. After takeoff, the drone hovers for 1 second, moves forward 0.5 m, hovers again, moves back 0.5 m, and then lands.</p>",
            "<p>Going a step further, we replace the content of the function with the following:</p>":
            "<p>To demonstrate turning and returning, replace <code>move_linear_simple</code> with the copyable version below:</p>",
            "<p>According to what we have learned about printing the flight data of the drone in real-time operation in the terminal, refer to the following code (the take_off_simple(scf) function and the param_deck_flow(name, value_str) function can be retained or have no content as shown below):</p>":
            "<p>The complete copyable program below records live position data. <code>log_pos_callback</code> updates the position estimate, while <code>param_deck_flow</code> checks whether the Flow deck is connected.</p>",
            "<p>Define and add a new function named move_box_limit, put it in the main function, and refer to the program as follows:</p>":
            "<p>The complete copyable program below includes <code>move_box_limit</code>. Before running it, confirm that position logging updates correctly and assign one team member to emergency-stop duty.</p>",
            "<p>Then redefine and add a function named move_box_limit and place it in the main function. The same reference program is as follows:</p>":
            "<p>The complete copyable program below includes <code>move_box_limit</code>. Before running it, confirm that position logging updates correctly and assign one team member to emergency-stop duty.</p>",
        }
    for old_text, new_text in paragraph_replacements.items():
        body = body.replace(old_text, new_text)
    return body


GROUP_URI_MANUALS = {
    "manual-04-multiranger",
    "manual-05-ranging",
    "manual-06-complex-map",
    "manual-07-autonomous-mapping-review",
    "manual-09-cflib",
    "manual-10-motion-commander",
    "manual-11-integrated-practice",
    "manual-12-position-commander",
    "manual-13-project-demo",
}


def group_uri_reminder(lang: str) -> str:
    if lang == "zh":
        return '''
<div class="admonition"><p class="admonition-title">运行前确认小组 URI</p>
<p>本实验的 Python 脚本统一从环境变量 <code>CFLIB_URI</code> 读取实验 3 中分配的完整 radio URI，不需要把小组地址重复写入每个代码文件。打开新终端后先执行：</p>
<pre><code>echo "$CFLIB_URI"</code></pre>
<p>输出必须与本组标签上的完整 URI 完全一致，包括接口编号、channel、速率和 address。若输出为空或不正确，请返回实验 3 的“将完整 URI 保存到虚拟机”步骤重新设置；确认无误后再运行本实验脚本。</p></div>
'''
    return '''
<div class="admonition"><p class="admonition-title">Confirm the Group URI Before Running</p>
<p>Python scripts in this experiment read the complete radio URI assigned in Experiment 3 from the <code>CFLIB_URI</code> environment variable. Do not copy the group address into every code file. In each new terminal, check it first:</p>
<pre><code>echo "$CFLIB_URI"</code></pre>
<p>The output must exactly match the complete URI on the group label, including the interface, channel, data rate, and address. If it is empty or incorrect, repeat the “Save the complete URI in the virtual machine” step in Experiment 3 before running the script.</p></div>
'''


def apply_group_uri_overrides(manual: Manual, lang: str, body: str) -> str:
    generic_uri = ""
    encoded_uri = ""

    body = body.replace(
        "from cflib.positioning.motion_commander import MotionCommander\n"
        "URI = &#x27;radio://0/80/250K&#x27;  #Change to your cf2&#x27;s URI",
        "from cflib.positioning.motion_commander import MotionCommander\n"
        "from cflib.utils import uri_helper\n"
        f"URI = uri_helper.uri_from_env(default=&#x27;{encoded_uri}&#x27;)",
    )
    body = body.replace(
        "# URI to the Crazyflie to connect to\n"
        "uri = &#x27;radio://0/80/2M/E7E7E7E7E7&#x27;",
        "from cflib.utils import uri_helper\n\n"
        f"uri = uri_helper.uri_from_env(default=&#x27;{encoded_uri}&#x27;)",
    )
    body = re.sub(
        r"uri_helper\.uri_from_env\(default=&#x27;radio://0/[0-9]+/(?:2M|1M|250K)/[0-9A-Fa-f]{10}&#x27;\)",
        f"uri_helper.uri_from_env(default=&#x27;{generic_uri}&#x27;)",
        body,
    )
    body = body.replace(
        "URI = uri_helper.uri_from_env(default=&#x27;&#x27;)",
        "URI = uri_helper.uri_from_env(default=&#x27;&#x27;)\n"
        "if not URI:\n"
        "    raise RuntimeError(&#x27;CFLIB_URI is empty; configure the group URI first.&#x27;)",
    )
    body = body.replace(
        "uri = uri_helper.uri_from_env(default=&#x27;&#x27;)",
        "uri = uri_helper.uri_from_env(default=&#x27;&#x27;)\n"
        "if not uri:\n"
        "    raise RuntimeError(&#x27;CFLIB_URI is empty; configure the group URI first.&#x27;)",
    )

    if manual.slug == "manual-06-complex-map":
        body = body.replace(
            "cd crazyflie-demos/demos/scripts/cflib/multiranger/multiranger_pointcloud\n"
            "python3 multiranger_pointcloud.py",
            "cd crazyflie-demos/demos/scripts/cflib/multiranger/multiranger_pointcloud\n"
            "echo &quot;$CFLIB_URI&quot;\n"
            "python3 multiranger_pointcloud.py",
        )
        if lang == "zh":
            body = body.replace(
                "<p>运行前请确认 Crazyflie、Crazyradio、Flow deck 和 Multi-ranger deck 已连接正常；该示例需要图形界面和 Python 可视化依赖",
                "<p>运行前请确认 Crazyflie、Crazyradio、Flow deck 和 Multi-ranger deck 已连接正常，并核对终端输出的是本组完整 URI；官方脚本通过 <code>uri_helper.uri_from_env()</code> 读取 <code>CFLIB_URI</code>。该示例需要图形界面和 Python 可视化依赖",
            )
        else:
            body = body.replace(
                "<p>Before running the demo, confirm that the Crazyflie, Crazyradio, Flow deck, and Multi-ranger deck are connected correctly. This example requires a graphical desktop and Python visualization dependencies",
                "<p>Before running the demo, confirm that the Crazyflie, Crazyradio, Flow deck, and Multi-ranger deck are connected correctly, and verify that the terminal prints the complete URI assigned to the group. The official script reads <code>CFLIB_URI</code> through <code>uri_helper.uri_from_env()</code>. This example requires a graphical desktop and Python visualization dependencies",
            )

    if manual.slug == "manual-03-crazyflie-setup":
        if lang == "zh":
            old = "<p>同时将要运行的python脚本放入workspace文件夹下，双击test.py脚本文件进行编辑，修改第14行的URI地址，与当前crazyradio的地址一致，修改完之后点击save按钮后退出。</p>"
            new = "<p>将 <code>test.py</code> 放入 <code>workspace</code> 文件夹。脚本通过 <code>uri_helper.uri_from_env()</code> 读取已经保存的 <code>CFLIB_URI</code>，不再在代码中手工填写小组地址。运行前先执行 <code>echo &quot;$CFLIB_URI&quot;</code>，确认输出与本组完整 URI 一致。</p>"
            body = body.replace(
                "<p>并且扫描到crazyradio之后，记住其radio的地址，如图所示为：//0/80/2M</p>",
                "<p>使用 Crazyradio 扫描和连接前，确认 cfclient 地址栏中的接口、channel、速率和 address 与本组完整 URI 一致；不能只核对 <code>//0/80/2M</code> 这一部分。</p>",
            )
        else:
            old = "<p>At the same time, put the python script to be run into the workspace folder, double-click the test.py script file to edit, modify the URI address on line 14 to be consistent with the current crazyradio address, click the save button after modification and exit.</p>"
            new = "<p>Place <code>test.py</code> in the <code>workspace</code> folder. The script reads the saved <code>CFLIB_URI</code> through <code>uri_helper.uri_from_env()</code>, so the group address is not entered manually in the code. Before running, use <code>echo &quot;$CFLIB_URI&quot;</code> and confirm that the output matches the complete URI assigned to the group.</p>"
            body = body.replace(
                "<p>And after scanning crazyradio, remember its radio address, as shown in the picture: //0/80/2M</p>",
                "<p>Before scanning and connecting through Crazyradio, confirm that the interface, channel, data rate, and address in the cfclient address field match the group&apos;s complete URI. Checking only <code>//0/80/2M</code> is not sufficient.</p>",
            )
        body = body.replace(old, new)
        body = re.sub(
            r'<figure><img src="\.\./assets/(?:images|images-en)/manual-03-crazyflie-setup/024\.png" alt="manual image" loading="lazy" decoding="async"></figure>',
            "",
            body,
        )
        return body

    if manual.slug not in GROUP_URI_MANUALS:
        return body
    reminder = group_uri_reminder(lang)
    sentinel = "运行前确认小组 URI" if lang == "zh" else "Confirm the Group URI Before Running"
    if sentinel not in body:
        body = re.sub(
            r'(<h1>.*?</h1>(?:<p class="subtitle">.*?</p>)?)',
            lambda match: match.group(1) + reminder,
            body,
            count=1,
            flags=re.DOTALL,
        )
    return body


def autonomous_mapping_section(lang: str) -> str:
    code_path = ROOT / "assets" / "code" / "auto_multiranger_pointcloud.py"
    escaped_code = html.escape(code_path.read_text(encoding="utf-8"))
    if lang == "zh":
        return f'''
<h3>实验：Multi-ranger 未知环境自主探索与建图</h3>
<p>本实验不再预先写入固定飞行轨迹。课程脚本根据 Multi-ranger 的前、后、左、右测距结果在线选择可通行方向，并利用 Flow deck 的位置估计记录已访问网格；飞行过程中持续生成二维障碍点云，达到时间或范围限制后在当前位置降落。</p>
<p><a href="../assets/code/auto_multiranger_pointcloud.py" download>下载课程代码：auto_multiranger_pointcloud.py</a></p>
<p>将文件保存到虚拟机的 <code>~/workspace</code>，确认实验 3 配置的小组 URI 后运行：</p>
<pre><code>cd ~/workspace
echo "$CFLIB_URI"
python3 auto_multiranger_pointcloud.py</code></pre>
<h3>探索与抗缝隙干扰逻辑</h3>
<ul>
<li>测距数据以 10 Hz 读取，并通过滑动中值滤波抑制单帧跳变；点云按 2.5 cm 网格去重，减少孤立噪点。</li>
<li>侧向距离突然变远时不会立即转弯。该方向必须连续保持开阔，并随无人机移动形成至少约 0.24 m 的有效开口宽度，才会被判定为可进入分支；普通通道侧壁距离不会被当作开口。</li>
<li>无人机每前进约 0.25 m 会停止并向左右各偏转 12° 检查前方宽度；两个探测方向均达到约 0.52 m 净空时才继续前进。该几何关系适配约 0.40-0.50 m 的单通道，同时仍可排除厘米级挡板拼缝。</li>
<li>在左右侧壁都位于 0.45 m 以内时，脚本根据左右测距差加入不超过 0.035 m/s 的横向修正，使无人机保持在窄通道中部；若单侧距离小于 0.10 m，则停止前进并向另一侧平移 0.04 m。</li>
<li>多个方向可通行时，脚本比较前方、左侧和右侧目标网格的访问次数，优先进入访问较少的方向；前方受阻时只使用已经确认的侧向开口或已飞过的后方路径。</li>
</ul>
<h3>运行参数与停止条件</h3>
<ul>
<li><code>FORWARD_SPEED_MPS = 0.12</code>：默认低速探索速度。</li>
<li><code>FORWARD_STOP_DISTANCE_M = 0.32</code>、<code>FRONT_EMERGENCY_DISTANCE_M = 0.18</code>：前方正常停止距离和紧急距离。</li>
<li><code>SIDE_EMERGENCY_DISTANCE_M = 0.10</code>：侧向紧急距离。该值与侧向开口判定分开，避免在 0.40-0.50 m 通道内误触发。</li>
<li><code>SIDE_OPEN_DISTANCE_M = 0.60</code>、<code>SIDE_OPEN_MIN_WIDTH_M = 0.24</code>：侧向分支的最小探测深度和连续宽度；若挡板缝隙仍造成误判，应优先增大宽度阈值。</li>
<li><code>MAX_RADIUS_FROM_START_M = 1.80</code>、<code>MAX_FLIGHT_TIME_S = 120</code>：相对起点的最大活动半径和最长飞行时间，必须按实际场地调整。</li>
</ul>
<div class="admonition"><p class="admonition-title">安全要求</p><p>Multi-ranger 是单点 ToF 测距装置，量程结果会受到目标表面和环境光等条件影响，抗缝隙处理只能降低误判概率，不能替代封闭场地和人工监护。首次运行时清空场地并安排一名组员专门观察飞行；按 <code>Escape</code> 或关闭地图窗口会请求停止探索并降落。若探测仍不稳定，应降低速度、增大开口宽度阈值或加装连续无缝挡板，不得依靠软件强行穿越可疑开口。硬件量程说明可直接查看 <a href="https://www.bitcraze.io/documentation/hardware/multi_ranger_deck/multi_ranger_deck-datasheet.pdf">Multi-ranger deck datasheet</a>。</p></div>
<p>以下场地图片用于核对实验环境。点云结果应能够反映外围挡板和内部隔断的主要轮廓；局部缺口、重影和漂移应在实验记录中说明，并结合滤波阈值、飞行速度及 Flow deck 累积误差分析原因。</p>
<figure><img src="../assets/images/manual-07-autonomous-mapping-review/002.png" alt="自主探索建图实验场地" loading="lazy" decoding="async"></figure>
<details><summary>查看完整课程代码</summary><pre><code>{escaped_code}</code></pre></details>
'''
    return f'''
<h3>Experiment: Multi-ranger Exploration and Mapping in an Unknown Environment</h3>
<p>This experiment no longer uses a predefined flight trajectory. The course script selects traversable directions online from the front, back, left, and right Multi-ranger measurements and uses Flow-deck position estimates to record visited cells. It builds a two-dimensional obstacle point cloud during flight and lands in place when the time or area limit is reached.</p>
<p><a href="../assets/code/auto_multiranger_pointcloud.py" download>Download the course script: auto_multiranger_pointcloud.py</a></p>
<p>Save the file in <code>~/workspace</code>, verify the group URI configured in Experiment 3, and run:</p>
<pre><code>cd ~/workspace
echo "$CFLIB_URI"
python3 auto_multiranger_pointcloud.py</code></pre>
<h3>Exploration and panel-gap rejection</h3>
<ul>
<li>Range data is read at 10 Hz and processed by a sliding median filter to suppress single-frame jumps. Point-cloud samples are deduplicated on a 2.5 cm grid to reduce isolated noise.</li>
<li>A sudden long side measurement does not trigger a turn. The direction must remain open while the aircraft travels across at least about 0.24 m of useful opening width before it is accepted as a branch. Normal side-wall distances inside a channel are not treated as openings.</li>
<li>After approximately every 0.25 m of forward travel, the aircraft stops and probes 12° to each side. It continues only when both probe headings provide about 0.52 m of clearance. This geometry supports a roughly 0.40-0.50 m single channel while continuing to reject centimetre-scale panel seams.</li>
<li>When both side walls are within 0.45 m, the script applies no more than 0.035 m/s of lateral correction from the left-right range difference to keep the aircraft near the channel centre. If one side falls below 0.10 m, it stops forward motion and shifts 0.04 m away from that wall.</li>
<li>When several directions are traversable, the script compares visit counts for the forward, left, and right target cells and prefers the less-visited direction. When the front is blocked, it uses only a confirmed side opening or the previously travelled path behind the aircraft.</li>
</ul>
<h3>Operating parameters and stopping conditions</h3>
<ul>
<li><code>FORWARD_SPEED_MPS = 0.12</code>: default low exploration speed.</li>
<li><code>FORWARD_STOP_DISTANCE_M = 0.32</code> and <code>FRONT_EMERGENCY_DISTANCE_M = 0.18</code>: normal forward stopping and emergency distances.</li>
<li><code>SIDE_EMERGENCY_DISTANCE_M = 0.10</code>: side emergency distance. It is separate from side-opening detection to avoid false emergency responses in a 0.40-0.50 m channel.</li>
<li><code>SIDE_OPEN_DISTANCE_M = 0.60</code> and <code>SIDE_OPEN_MIN_WIDTH_M = 0.24</code>: minimum side-branch depth and continuous width. Increase the width threshold first if panel seams still cause false detections.</li>
<li><code>MAX_RADIUS_FROM_START_M = 1.80</code> and <code>MAX_FLIGHT_TIME_S = 120</code>: maximum radius from the start and maximum flight time. Adjust both to the actual test area.</li>
</ul>
<div class="admonition"><p class="admonition-title">Safety requirements</p><p>The Multi-ranger uses single-point ToF measurements, and measured range depends on target surfaces and ambient-light conditions. Gap rejection reduces the probability of a false opening but does not replace an enclosed test area or a supervising operator. Clear the area for the first run and assign one team member to watch the aircraft. Pressing <code>Escape</code> or closing the map window requests an exploration stop and landing. If detection remains unstable, reduce speed, increase the opening-width threshold, or use continuous gap-free barriers; do not force the aircraft through an uncertain opening. See the direct <a href="https://www.bitcraze.io/documentation/hardware/multi_ranger_deck/multi_ranger_deck-datasheet.pdf">Multi-ranger deck datasheet</a> for the hardware range specification.</p></div>
<p>Use the following image to verify the experimental environment. The resulting point cloud should reproduce the main outline of the outer barrier and internal partitions. Document local gaps, duplicate edges, and drift, and relate them to filtering thresholds, flight speed, and accumulated Flow-deck error.</p>
<figure><img src="../assets/images/manual-07-autonomous-mapping-review/002.png" alt="Autonomous exploration and mapping test area" loading="lazy" decoding="async"></figure>
<details><summary>View the complete course script</summary><pre><code>{escaped_code}</code></pre></details>
'''


def apply_autonomous_mapping_overrides(lang: str, body: str) -> str:
    if lang == "zh":
        pattern = r'<h3>实验：自主建图</h3>.*?(?=<h2>复习</h2>)'
    else:
        pattern = r'<h3>Experiment: Autonomous mapping</h3>.*?(?=<h2>Review</h2>)'
    return re.sub(
        pattern,
        lambda _match: autonomous_mapping_section(lang),
        body,
        count=1,
        flags=re.DOTALL,
    )


def apply_competition_rules_override(lang: str, body: str) -> str:
    if lang == "zh":
        old = '''<p>S:最终成绩（m），越小越好</p>
<p>v:无人机在整个任务流程中设置的恒定的速度（m/s）</p>
<p>:无人机在整个任务流程中从在起点开始在xy平面上开始移动到开始降落的计时（s）</p>
<p>:在代码中为了稳定无人机姿态，在无人机每进行一步移动后调用time.sleep的总时间（s）,在起飞前给老师确认代码时，确定这些时间。</p>
<p>Reward:R2和R3的奖励值为1.4m，R4的奖励值为4.9m，R1的奖励值为1.05m</p>
<p>Punish:最终降落在A区时的位置不规范，惩罚0.35m</p>'''
        new = '''<div class="admonition"><p class="admonition-title">创意板块计分公式</p>
<p><strong>S = v &times; (t<sub>1</sub> - t<sub>2</sub>) - Reward + Punish</strong></p>
<ul>
<li><code>S</code>：最终成绩（m），数值越小越好。</li>
<li><code>v</code>：整个任务流程中设置的恒定飞行速度（m/s）。</li>
<li><code>t<sub>1</sub></code>：无人机从起点开始在 xy 平面移动，到开始降落之间的现场计时（s）。</li>
<li><code>t<sub>2</sub></code>：代码中每一步移动后为稳定姿态而调用 <code>time.sleep</code> 的总时长（s），起飞前由教师根据代码确认。</li>
<li><code>Reward</code>：R2、R3 各奖励 1.4 m，R4 奖励 4.9 m，R1 奖励 1.05 m；满足对应条件的奖励累加后代入公式。</li>
<li><code>Punish</code>：最终在 A 区降落但位置不规范时计 0.35 m；无此情况时为 0。</li>
</ul></div>'''
    else:
        old = '''<p>S: Final score (m), the smaller the better</p>
<p>v: The constant speed (m/s) set by the drone throughout the mission process</p>
<p>: The timing of the drone starting to move on the xy plane from the starting point to landing in the entire mission process (s)</p>
<p>: In order to stabilize the attitude of the drone in the code, the total time (s) of time.sleep is called after each step of the drone&#x27;s movement. These times are determined when confirming the code with the teacher before taking off.</p>
<p>Reward: The reward value of R2 and R3 is 1.4m, the reward value of R4 is 4.9m, and the reward value of R1 is 1.05m</p>
<p>Punish: The position when finally landing in area A was irregular and the penalty was 0.35m.</p>'''
        new = '''<div class="admonition"><p class="admonition-title">Creative-section scoring formula</p>
<p><strong>S = v &times; (t<sub>1</sub> - t<sub>2</sub>) - Reward + Punish</strong></p>
<ul>
<li><code>S</code>: final score in metres; a lower value is better.</li>
<li><code>v</code>: constant flight speed used throughout the task, in m/s.</li>
<li><code>t<sub>1</sub></code>: measured time from the first xy-plane movement at the start until landing begins, in seconds.</li>
<li><code>t<sub>2</sub></code>: total duration of the <code>time.sleep</code> calls placed after movement steps to stabilize the aircraft, in seconds; the instructor confirms this value from the code before takeoff.</li>
<li><code>Reward</code>: 1.4 m each for R2 and R3, 4.9 m for R4, and 1.05 m for R1. Add all rewards earned before substituting the value into the formula.</li>
<li><code>Punish</code>: 0.35 m for a non-standard landing position inside Area A; otherwise 0.</li>
</ul></div>'''
    body = body.replace(old, new)
    if lang == "zh":
        creative_intro = '<p>该板块的展示任务希望同学们根据学习到的 Crazyflie 无人机传感器应用知识以及相应的软件编程知识来完成，不限定使用何种传感器或程序模块，鼓励同学们在规则基础上发挥创意，以更优策略完成任务。</p>'
        creative_summary = '''
<h3>规则摘要</h3>
<table><tbody>
<tr><th>项目</th><th>创意板块规则</th></tr>
<tr><td>任务路线</td><td>从 A 区起飞，经过 B、C 区后返回 A 区降落；B、C 的先后顺序不限。</td></tr>
<tr><td>速度</td><td>全程采用同一个恒定速度，且必须低于 <code>0.3 m/s</code>。</td></tr>
<tr><td>高度</td><td>飞行高度不得高于挡板顶沿，场地挡板高度为 <code>45 cm</code>。</td></tr>
<tr><td>碰撞</td><td>单次有效任务最多允许 2 次明确碰撞；发生第 3 次碰撞时，本次任务立即失效。</td></tr>
<tr><td>奖励点</td><td>R1、R2、R3、R4 均为奖励点。R1 位于起终点 A 区，同样计入奖励。</td></tr>
<tr><td>成绩方向</td><td>按计分公式计算，最终数值越小越好。</td></tr>
</tbody></table>'''
        speed_intro = '<p>该板块的展示主题为“速度”，最快完成任务即为最优。但是同学们一定要注意飞行安全，同时也要尽量保证无人机硬件的安全与完整。</p>'
        speed_replacement = '''<p>该板块以完成时间为主要排序依据，不设置比赛速度上限，但必须同时满足高度和零碰撞要求。任何一次明确碰撞都会使本次竞速成绩失效。</p>
<h3>规则摘要</h3>
<table><tbody>
<tr><th>项目</th><th>竞速板块规则</th></tr>
<tr><td>任务路线</td><td>从图示起点起飞，进入终点区域并完成降落。</td></tr>
<tr><td>速度</td><td>不设速度上限；参赛组自行确定速度和控制策略。</td></tr>
<tr><td>高度</td><td>飞行高度不得高于挡板顶沿，场地挡板高度为 <code>45 cm</code>。</td></tr>
<tr><td>碰撞</td><td>不允许碰撞；发生任何一次明确碰撞，本次成绩立即失效。</td></tr>
<tr><td>计时</td><td>从无人机离开地面开始，到在终点区域完全降落并静止为止。</td></tr>
<tr><td>成绩方向</td><td>计入落点罚时后，用时越短越好。</td></tr>
</tbody></table>'''
        replacements = {
            '<p>奖励机制：无人机的飞行路径经过了R2、R3、R4都会获得奖励。</p>': '<p>奖励机制：R1、R2、R3、R4 均设置奖励。R1 位于起终点 A 区；R2、R3、R4 分布在任务路径中。每个奖励点在单次任务中最多计入一次。</p>',
            '<p>希望同学们考虑整体无人机飞行路径的代价：飞行路径长度+奖励</p>': '<p>创意板块的成绩同时考虑有效飞行距离、奖励和降落惩罚，具体以展示流程中的计分公式为准。</p>',
            '<p>整个飞行过程中无人机的高度不能超过挡板的高度，且不能与挡板发生碰撞（极其轻微的刮擦不算），否则算作此次飞行任务失败。</p>': '<p>整个飞行过程中，无人机飞行高度不得高于挡板顶沿（45 cm）。单次任务最多允许 2 次明确碰撞；发生第 3 次碰撞时，本次飞行任务立即失效。极轻微擦碰不计入碰撞次数；是否构成明确碰撞以教师现场判定和视频记录为准。碰撞次数不直接代入计分公式，只用于判断本次任务是否有效。</p>',
            '<p>对于R2、R3、R4区域，在飞行过程中无人机的垂直方向上的投影经过了该区域则可以获得该区域的奖励，无人机降落时静止在地面上的投影有两个电机的部分位于R1区域则可以获得该区域的奖励。</p>': '<p>R1、R2、R3、R4 均可获得奖励。对于 R2、R3、R4，无人机在飞行过程中的垂直投影经过对应区域即可获得该区域奖励；R1 位于起终点 A 区，无人机最终降落并静止后，至少两个电机的投影位于 R1 区域内或边界上，即可获得 R1 奖励。每个奖励点在单次任务中只计一次。</p>',
            '<p>大体的任务要求如下：无人机在如图所示的起点任意位置开始起飞，降落在终点的区域。从无人机开始起飞离开地面开始计时，到无人机完全降落静止在终点区域为止。所用时间更少成绩更好。不限制飞行高度，但是一定要注意飞行安全！注意保护无人机硬件不被损坏！</p>': '<p>无人机从图示起点区域内任意位置起飞，并在终点区域完成降落。竞速板块不设置速度上限；飞行高度不得高于挡板顶沿（45 cm）。从无人机离开地面开始计时，到无人机在终点区域完全降落并静止时停止计时。发生任何一次明确碰撞时，本次成绩立即失效，不再继续计时排名。</p>',
            '<p>最终无人机是否降落在终点的评判标准为，无人机至少有两个电机的位置处于终点区域内，在边界上也算。如果没有达到上述标准，但是至少有一个电机的位置处于终点区域内或者位于边界上，罚时5秒计入成绩。其它的降落情况都不计入成绩。</p>': '<p>有效竞速任务必须全程保持在挡板顶沿以下且没有发生碰撞。最终降落时，至少两个电机位于终点区域内或边界上，视为正常完成；若只有一个电机位于终点区域内或边界上，成绩增加 5 秒罚时；其它降落情况均视为本次成绩失效。</p>',
        }
    else:
        creative_intro = '<p>The display tasks in this section are expected to be completed by students based on the Crazyflie drone sensor application knowledge and corresponding software programming knowledge they have learned. There are no restrictions on which sensors or program modules to use. Students are encouraged to be creative based on the rules and complete the tasks with better strategies.</p>'
        creative_summary = '''
<h3>Rule summary</h3>
<table><tbody>
<tr><th>Item</th><th>Creative-section rule</th></tr>
<tr><td>Route</td><td>Take off from Area A, pass through Areas B and C in either order, and return to Area A to land.</td></tr>
<tr><td>Speed</td><td>Use one constant speed throughout the run, and keep it below <code>0.3 m/s</code>.</td></tr>
<tr><td>Height</td><td>Do not fly above the top edge of the arena baffles, which are <code>45 cm</code> high.</td></tr>
<tr><td>Collisions</td><td>A valid run may contain at most two confirmed collisions. The third collision immediately invalidates the run.</td></tr>
<tr><td>Reward zones</td><td>R1, R2, R3, and R4 are all reward zones. R1 is located inside the start/finish Area A and also earns a reward.</td></tr>
<tr><td>Ranking</td><td>Apply the scoring formula; a lower final value is better.</td></tr>
</tbody></table>'''
        speed_intro = '<p>The display theme of this section is &quot;speed&quot;, and the fastest completion of the task is the best. However, students must pay attention to flight safety and try to ensure the safety and integrity of the drone hardware.</p>'
        speed_replacement = '''<p>This section is ranked primarily by completion time. There is no competition speed limit, but the height and zero-collision requirements remain mandatory. Any confirmed collision invalidates the current speed-trial result.</p>
<h3>Rule summary</h3>
<table><tbody>
<tr><th>Item</th><th>Speed-section rule</th></tr>
<tr><td>Route</td><td>Take off from the indicated start area, enter the finish area, and complete the landing.</td></tr>
<tr><td>Speed</td><td>No speed limit; each team selects its own speed and control strategy.</td></tr>
<tr><td>Height</td><td>Do not fly above the top edge of the arena baffles, which are <code>45 cm</code> high.</td></tr>
<tr><td>Collisions</td><td>No collisions are allowed. Any confirmed collision immediately invalidates the run.</td></tr>
<tr><td>Timing</td><td>From the moment the aircraft leaves the ground until it has fully landed and stopped inside the finish area.</td></tr>
<tr><td>Ranking</td><td>After any landing-time penalty is added, a shorter time is better.</td></tr>
</tbody></table>'''
        replacements = {
            '<p>Reward mechanism: The drone&#x27;s flight path will receive rewards if it passes through R2, R3, and R4.</p>': '<p>Reward mechanism: R1, R2, R3, and R4 all carry rewards. R1 is located inside the start/finish Area A, while R2, R3, and R4 are distributed along the task route. Each reward zone may be counted only once in a run.</p>',
            '<p>I hope students will consider the cost of the overall drone flight path: flight path length + reward</p>': '<p>The creative-section score combines effective flight distance, earned rewards, and the landing penalty, as defined by the scoring formula below.</p>',
            '<p>During the entire flight, the height of the drone cannot exceed the height of the baffle, and it cannot collide with the baffle (extremely slight scratches do not count), otherwise the flight mission will be considered a failure.</p>': '<p>Throughout the run, the aircraft must remain below the top edge of the 45 cm baffles. A run may contain at most two confirmed collisions; the third collision immediately invalidates the run. Extremely light brushing contact is not counted as a collision. The instructor determines confirmed collisions from on-site observation and the video record. Collision count is not substituted into the scoring formula; it is used only to determine whether the run remains valid.</p>',
            '<p>For R2, R3, and R4 areas, if the vertical projection of the drone passes through this area during flight, you can get rewards in this area. When the drone lands, the part of the projection that is stationary on the ground and has two motors is in the R1 area, you can get rewards in this area.</p>': '<p>R1, R2, R3, and R4 can all earn rewards. For R2, R3, and R4, the reward is earned when the aircraft&#x27;s vertical projection passes through the corresponding zone. R1 is inside the start/finish Area A; its reward is earned when, after the final landing, the projection of at least two motors lies inside R1 or on its boundary. Each reward zone is counted only once per run.</p>',
            '<p>The general mission requirements are as follows: the drone takes off from any starting point as shown in the figure and lands at the end point. The timing starts from the time when the drone takes off and leaves the ground, until the drone completely lands and remains stationary in the end area. Less time spent, better results. There is no flight height limit, but you must pay attention to flight safety! Pay attention to protect the drone hardware from damage!</p>': '<p>The aircraft takes off from any position inside the indicated start area and lands inside the finish area. The speed section has no speed limit, but the aircraft must remain below the top edge of the 45 cm baffles. Timing starts when the aircraft leaves the ground and stops when it has completely landed and become stationary inside the finish area. Any confirmed collision immediately invalidates the run, which is then excluded from the time ranking.</p>',
            '<p>The final criterion for judging whether the drone lands at the end point is that the position of at least two motors of the drone is within the end point area, including on the boundary. If the above criteria are not met, but at least one motor is located within the finish area or on the boundary, a 5-second penalty will be included in the score. Other landing situations will not be included in the score.</p>': '<p>A valid speed run must remain below the baffle height and contain no collisions. At the final landing, at least two motors must be inside the finish area or on its boundary for a normal completion. If only one motor is inside the finish area or on its boundary, add a 5-second penalty. All other landing outcomes invalidate the run.</p>',
        }
    if "Creative-section rule" not in body and "创意板块规则" not in body:
        body = body.replace(creative_intro, creative_intro + creative_summary)
    body = body.replace(speed_intro, speed_replacement)
    for source, replacement in replacements.items():
        body = body.replace(source, replacement)
    if lang == "zh":
        challenge_marker = '<h2>最终综合展示评价说明</h2>'
        challenge_section = '''<h2>挑战板块（20% 附加分）</h2>
<p>挑战板块为自愿参加的附加任务，满分上限为基础综合评价满分的 20%。不参加或挑战未形成有效成绩，不扣除创意板块和竞速板块已经获得的基础成绩。</p>
<div class="admonition"><p class="admonition-title">核心变化：开口位置赛前未知</p>
<p>挑战任务建立在创意板块规则之上。A、B、C 任务区域及 R1、R2、R3、R4 奖励点的位置保持固定；贴靠场地外墙的挡板保持固定，仅朝向场地内部的挡板段和开口会由助教在每次挑战前调整。参赛组在起飞前不能获知、查看或试飞当次布局。</p></div>
<figure class="wide-figure"><img src="../assets/images/manual-13-project-demo/challenge-variable-openings.png" alt="挑战板块固定任务区域与可变挡板开口示意图" loading="lazy" decoding="async"><figcaption><strong>挑战板块场地示意</strong><span>A、B、C 与 R1-R4 的位置固定，贴靠场地外墙的挡板不变。橙色标记仅表示 A、B、C 朝向场地内部一侧的开口可能调整；正式挑战的开口位置由助教赛前设置，起飞前不公布。</span></figcaption></figure>
<h3>挑战规则</h3>
<ul>
<li>沿用创意板块的任务路线、计分公式和奖励数值：从 A 区起飞，经过 B、C 后返回 A 区，R1-R4 均可计入奖励。</li>
<li>沿用创意板块的飞行限制：全程恒定速度且低于 <code>0.3 m/s</code>，飞行高度不得高于 45 cm 挡板顶沿，单次任务最多允许 2 次明确碰撞。</li>
<li>A、B、C 和 R1-R4 的位置固定，贴靠场地外墙的挡板也保持固定；仅朝向场地内部的挡板段、通道方向及开口位置可以变化，当次布局以助教完成的现场摆放为准。</li>
<li>参赛代码应根据飞行中的传感器数据识别可通行方向。仅依赖预先写死的挡板坐标或固定开口位置，不能满足挑战要求。</li>
<li>挑战成绩仍使用创意板块公式计算，数值越小越好；有效挑战成绩用于单独核算最高 20% 的附加分。</li>
</ul>
<h3>挑战流程</h3>
<ol>
<li>小组完成代码、硬件和急停检查后，先通知助教，不得自行开始挑战。</li>
<li>助教仅调整 A、B、C 朝向场地内部一侧的挡板和开口位置，贴靠场地外墙的挡板不作调整；参赛组在起飞前不得查看布局或进行试飞。</li>
<li>助教确认场地安全并开始协助录像后，通知小组起飞。录像应完整覆盖起飞、经过 B/C、奖励点判定、碰撞情况和返回 A 区降落。</li>
<li>任务结束后，由助教记录当次布局、计时、奖励点、碰撞次数、降落位置和任务是否有效。</li>
</ol>
'''
        evaluation_replacements = {
            '<p>原则上两个板块（创意+竞速）的展示表现各占50%，综合评价指数计算如下：</p>': '<p>基础综合评价仍由创意板块和竞速板块各占 50% 组成；挑战板块在基础评价之外单独提供最高 20% 的附加分。</p>',
            '<p>最终，综合评价指数越小的组别，综合项目展示评价越好。</p>': '<p>基础综合评价指数越小，基础评价越好。挑战附加分在基础评价完成后单独记录；不参加挑战或挑战成绩失效时，附加分记为 0，但不倒扣基础评价。</p>',
        }
    else:
        challenge_marker = '<h2>Final integrated demonstration evaluation</h2>'
        challenge_section = '''<h2>Challenge Section (20% Bonus)</h2>
<p>The challenge section is optional and can add up to 20% of the maximum base evaluation score. Choosing not to participate, or failing to record a valid challenge result, does not reduce the base score already earned from the creative and speed sections.</p>
<div class="admonition"><p class="admonition-title">Core change: opening positions are unknown before takeoff</p>
<p>The challenge is based on the creative-section rules. The A, B, and C task zones and the R1, R2, R3, and R4 reward zones remain fixed. Baffles against the outer arena walls also remain fixed; only inward-facing baffle segments and openings are adjusted by a teaching assistant before each challenge. Teams may not know, inspect, or test-fly the current layout before takeoff.</p></div>
<figure class="wide-figure"><img src="../assets/images-en/manual-13-project-demo/challenge-variable-openings.png" alt="Challenge schematic with fixed task zones and variable inward-facing baffle openings" loading="lazy" decoding="async"><figcaption><strong>Challenge Arena Schematic</strong><span>A, B, C, and R1-R4 remain fixed, as do baffles against the outer arena walls. Orange marks indicate only the possible adjustments to inward-facing openings around A, B, and C. Teaching assistants set these openings before the run, and the layout is not disclosed before takeoff.</span></figcaption></figure>
<h3>Challenge rules</h3>
<ul>
<li>Use the creative-section route, scoring formula, and reward values: take off from A, pass through B and C, return to A, and count any R1-R4 rewards earned.</li>
<li>Use the creative-section flight limits: one constant speed below <code>0.3 m/s</code>, flight below the top edge of the 45 cm baffles, and no more than two confirmed collisions in a run.</li>
<li>A, B, C, and R1-R4 remain fixed, and baffles against the outer arena walls also remain fixed. Only inward-facing baffle segments, corridor directions, and opening positions may change; the layout prepared by the teaching assistant is authoritative.</li>
<li>The program must identify traversable directions from sensor data during flight. A route that depends only on hard-coded baffle coordinates or fixed opening positions does not meet the challenge requirement.</li>
<li>The creative-section formula is also used for the challenge, and a lower result is better. A valid challenge result is used to calculate the separate bonus of up to 20%.</li>
</ul>
<h3>Challenge procedure</h3>
<ol>
<li>After completing code, hardware, and emergency-stop checks, notify a teaching assistant before starting the challenge.</li>
<li>The teaching assistant adjusts only the inward-facing baffles and openings around A, B, and C; baffles against the outer arena walls are not moved. The team may not inspect the layout or perform a test flight before takeoff.</li>
<li>After confirming arena safety and starting the recording, the teaching assistant authorizes takeoff. The recording must cover takeoff, traversal of B/C, reward-zone decisions, collisions, and the return landing in A.</li>
<li>After the run, the teaching assistant records the layout, elapsed time, reward zones, collision count, landing position, and whether the result is valid.</li>
</ol>
'''
        evaluation_replacements = {
            '<p>In principle, the display performance of the two sections (creative + racing) each accounts for 50%. The comprehensive evaluation index is calculated as follows:</p>': '<p>The base evaluation continues to assign 50% to the creative section and 50% to the speed section. The challenge section provides a separate bonus of up to 20% beyond the base evaluation.</p>',
            '<p>Ultimately, the smaller the comprehensive evaluation index of the group, the better the comprehensive project display evaluation.</p>': '<p>A lower base evaluation index is better. The challenge bonus is recorded separately after the base evaluation. If a team does not enter the challenge or its challenge result is invalid, the bonus is zero and the base evaluation is not reduced.</p>',
        }
    if "Challenge Section (20% Bonus)" not in body and "挑战板块（20% 附加分）" not in body:
        body = body.replace(challenge_marker, challenge_section + challenge_marker)
    for source, replacement in evaluation_replacements.items():
        body = body.replace(source, replacement)
    return body


def apply_manual_overrides(manual: Manual, lang: str, body: str) -> str:
    if manual.slug == FINAL_TEST_SLUG:
        return apply_competition_rules_override(lang, body)
    if manual.slug == "manual-01-vm":
        return apply_vm_manual_overrides(lang, body)
    if manual.slug == "manual-07-autonomous-mapping-review":
        return apply_autonomous_mapping_overrides(lang, body)
    if manual.slug == "manual-09-cflib":
        return apply_cflib_copyable_code_overrides(lang, body)
    if manual.slug != "manual-03-crazyflie-setup":
        return body
    if lang == "zh":
        cleanup_pairs = {
            "<h3>实验一：将cfclient的软件安装包拷贝到虚拟机的workspace文件夹中进行安装步骤</h3>": "<h3>实验一：使用 Git 获取 cfclient 指定版本并安装</h3>",
            "<p>此时再点击绿色的extract按键</p>": "",
            "<p>点击进入解压好的目录中，右键界面空白处选择open in terminal呼出终端。</p>": "",
        }
        image_root = "images"
    else:
        cleanup_pairs = {
            "<h3>Experiment 1: Copy the cfclient software installation package to the workspace folder of the virtual machine and proceed with the installation steps.</h3>": "<h3>Experiment 1: Use Git to obtain the specified cfclient version and install it</h3>",
            "<p>At this point click the green extract button</p>": "",
            "<p>Click to enter the decompressed directory, right-click on a blank space on the interface and select open in terminal to call out the terminal.</p>": "",
        }
        image_root = "images-en"
    for old_text, new_text in cleanup_pairs.items():
        body = body.replace(old_text, new_text)
    for index in range(1, 5):
        figure = f'<figure><img src="../assets/{image_root}/manual-03-crazyflie-setup/{index:03d}.png" alt="manual image" loading="lazy" decoding="async"></figure>'
        body = body.replace(figure, "")
    image = '<figure><img src="../assets/images/manual-03-crazyflie-setup/009.png" alt="manual image" loading="lazy" decoding="async"></figure>'
    if lang == "zh":
        old = f'''<p>\u518d\u8f93\u5165\u4ee5\u4e0b\u547d\u4ee4\u66f4\u65b0\u8f6f\u4ef6\u5de5\u5177\uff1a</p>
<p>pip3 install --upgrade pip setuptools wheel</p>
{image}
<p>\u6700\u540e\u8f93\u5165\u4ee5\u4e0b\u547d\u4ee4\u8fdb\u884c\u603b\u7684\u8f6f\u4ef6\u4f9d\u8d56\u5b89\u88c5\u6574\u7406\uff1a</p>
<pre><code>pip3 install -e .</code></pre>'''
        new = f'''<p>Ubuntu 20.04 \u9ed8\u8ba4\u4f7f\u7528 Python 3.8\uff0c\u8be5\u73af\u5883\u4e2d\u4e0d\u5e94\u65e0\u7248\u672c\u9650\u5236\u5730\u5347\u7ea7\u6253\u5305\u5de5\u5177\u3002<code>setuptools 71.x</code> \u4e0e\u65e7\u7248 <code>importlib_metadata</code> \u540c\u65f6\u5b58\u5728\u65f6\uff0c\u540e\u7eed\u5b89\u88c5\u53ef\u80fd\u51fa\u73b0 <code>AttributeError: module &#x27;importlib_metadata&#x27; has no attribute &#x27;EntryPoints&#x27;</code>\uff1b\u8f83\u65b0\u7684 <code>pip</code> \u548c <code>testresources</code> \u4e5f\u5df2\u505c\u6b62\u652f\u6301 Python 3.8\u3002\u4ee5\u4e0b\u547d\u4ee4\u56fa\u5b9a\u4e00\u7ec4\u517c\u5bb9\u7248\u672c\u3002\u5176\u4e2d\uff0c<code>testresources</code> \u7528\u4e8e\u8865\u9f50 <code>launchpadlib</code> \u7684\u4f9d\u8d56\uff0c\u4e0e <code>EntryPoints</code> \u62a5\u9519\u4e0d\u662f\u540c\u4e00\u95ee\u9898\u3002</p>
<pre><code>python3 -m pip install --user --upgrade &quot;pip==24.3.1&quot; &quot;setuptools==70.3.0&quot; &quot;wheel==0.45.1&quot; &quot;importlib-metadata==8.5.0&quot; &quot;testresources==2.0.1&quot;</code></pre>
{image}
<div class="admonition warning"><p class="admonition-title">\u6545\u969c\u5904\u7406</p><p>\u5982\u679c\u5df2\u7ecf\u6267\u884c\u8fc7\u65e0\u7248\u672c\u9650\u5236\u7684\u5347\u7ea7\u547d\u4ee4\uff0c\u5e76\u5728 <code>python3 -m pip install --user -e .</code> \u65f6\u770b\u5230\u4e0a\u8ff0 <code>EntryPoints</code> \u62a5\u9519\uff0c\u8bf7\u91cd\u65b0\u6267\u884c\u4e0a\u9762\u7684\u56fa\u5b9a\u7248\u672c\u547d\u4ee4\u3002\u547d\u4ee4\u6210\u529f\u540e\uff0c\u56de\u5230 <code>crazyflie-clients-python</code> \u76ee\u5f55\u7ee7\u7eed\u6267\u884c\u4e0b\u9762\u7684\u5b89\u88c5\u547d\u4ee4\u3002</p></div>
<p>\u6700\u540e\u8f93\u5165\u4ee5\u4e0b\u547d\u4ee4\u8fdb\u884c\u603b\u7684\u8f6f\u4ef6\u4f9d\u8d56\u5b89\u88c5\u6574\u7406\uff1a</p>
<pre><code>python3 -m pip install --user -e .</code></pre>'''
        body = body.replace(old, new)
        marker = '<h3>\u5b9e\u9a8c\u56db\uff1a\u4f7f\u7528python\u811a\u672c\u8ba9\u65e0\u4eba\u673a\u81ea\u4e3b\u8d77\u98de</h3>'
        radio_section = '''<h3>\u591a\u7ec4\u540c\u65f6\u5b9e\u9a8c\u7684\u65e0\u7ebf\u9891\u6bb5\u89c4\u5212</h3>
<p>\u6b63\u5f0f\u5b9e\u9a8c\u4e2d\u5982\u679c 12 \u7ec4\u5728\u540c\u4e00\u623f\u95f4\u540c\u65f6\u4f7f\u7528 Crazyradio\uff0c\u5efa\u8bae\u4e3a\u6bcf\u7ec4\u56fa\u5b9a\u4e00\u5957\u5b8c\u6574\u7684 radio URI\u3002URI \u683c\u5f0f\u4e3a <code>radio://\u63a5\u53e3\u7f16\u53f7/\u4fe1\u9053/\u901f\u7387/\u5730\u5740</code>\uff0c\u4f8b\u5982 <code>radio://0/60/2M/E7E7E7E7A6</code>\u3002\u5176\u4e2d\uff0c\u4fe1\u9053\u7528\u4e8e\u51cf\u5c11\u540c\u9891\u65e0\u7ebf\u62e5\u585e\uff0c\u5730\u5740\u7528\u4e8e\u907f\u514d\u8bef\u8fde\u5230\u5176\u4ed6\u7ec4\u7684\u65e0\u4eba\u673a\uff1b\u53ea\u4fee\u6539\u5730\u5740\u4e0d\u80fd\u5b8c\u5168\u89e3\u51b3\u540c\u9891\u5e72\u6270\u95ee\u9898\u3002</p>
<table><tbody>
<tr><th>\u7ec4\u522b</th><th>Channel</th><th>Address</th><th>\u5b8c\u6574 URI</th></tr>
<tr><td>1\u7ec4 / A\u7ec4</td><td>10</td><td><code>E7E7E7E7A1</code></td><td><code>radio://0/10/2M/E7E7E7E7A1</code></td></tr>
<tr><td>2\u7ec4 / B\u7ec4</td><td>20</td><td><code>E7E7E7E7A2</code></td><td><code>radio://0/20/2M/E7E7E7E7A2</code></td></tr>
<tr><td>3\u7ec4 / C\u7ec4</td><td>30</td><td><code>E7E7E7E7A3</code></td><td><code>radio://0/30/2M/E7E7E7E7A3</code></td></tr>
<tr><td>4\u7ec4 / D\u7ec4</td><td>40</td><td><code>E7E7E7E7A4</code></td><td><code>radio://0/40/2M/E7E7E7E7A4</code></td></tr>
<tr><td>5\u7ec4 / E\u7ec4</td><td>50</td><td><code>E7E7E7E7A5</code></td><td><code>radio://0/50/2M/E7E7E7E7A5</code></td></tr>
<tr><td>6\u7ec4 / F\u7ec4</td><td>60</td><td><code>E7E7E7E7A6</code></td><td><code>radio://0/60/2M/E7E7E7E7A6</code></td></tr>
<tr><td>7\u7ec4 / G\u7ec4</td><td>70</td><td><code>E7E7E7E7A7</code></td><td><code>radio://0/70/2M/E7E7E7E7A7</code></td></tr>
<tr><td>8\u7ec4 / H\u7ec4</td><td>80</td><td><code>E7E7E7E7A8</code></td><td><code>radio://0/80/2M/E7E7E7E7A8</code></td></tr>
<tr><td>9\u7ec4 / I\u7ec4</td><td>90</td><td><code>E7E7E7E7A9</code></td><td><code>radio://0/90/2M/E7E7E7E7A9</code></td></tr>
<tr><td>10\u7ec4 / J\u7ec4</td><td>100</td><td><code>E7E7E7E7AA</code></td><td><code>radio://0/100/2M/E7E7E7E7AA</code></td></tr>
<tr><td>11\u7ec4 / K\u7ec4</td><td>110</td><td><code>E7E7E7E7AB</code></td><td><code>radio://0/110/2M/E7E7E7E7AB</code></td></tr>
<tr><td>12\u7ec4 / L\u7ec4</td><td>120</td><td><code>E7E7E7E7AC</code></td><td><code>radio://0/120/2M/E7E7E7E7AC</code></td></tr>
</tbody></table>
<p>\u914d\u7f6e\u65f6\u5148\u7528 USB \u5355\u72ec\u8fde\u63a5\u4e00\u67b6\u65e0\u4eba\u673a\uff0c\u5728 cfclient \u4e2d\u8fde\u63a5 <code>usb://0</code>\uff0c\u8fdb\u5165 <code>Connect - Configure 2.x</code>\uff0c\u5199\u5165\u8be5\u7ec4\u5206\u914d\u7684 Radio channel \u548c Radio address\uff0c\u4fdd\u5b58\u540e\u91cd\u542f\u65e0\u4eba\u673a\u3002\u8fd9\u4e2a\u64cd\u4f5c\u53ea\u4fee\u6539\u65e0\u4eba\u673a\u7684\u65e0\u7ebf\u914d\u7f6e\uff0c\u4e0d\u4f1a\u81ea\u52a8\u540c\u6b65\u5230 Python \u4ee3\u7801\u6216\u865a\u62df\u673a\u3002</p>
<h4>\u5c06\u5b8c\u6574 URI \u4fdd\u5b58\u5230\u865a\u62df\u673a</h4>
<p>\u6bcf\u7ec4\u5728\u81ea\u5df1\u7684\u865a\u62df\u673a\u4e2d\u6267\u884c\u4e00\u6b21\u4e0b\u9762\u7684\u547d\u4ee4\u3002\u7ec8\u7aef\u51fa\u73b0\u63d0\u793a\u540e\uff0c\u4ece\u4e0a\u8868\u590d\u5236\u5e76\u7c98\u8d34\u672c\u7ec4\u7684\u5b8c\u6574 URI\uff0c\u4e0d\u8981\u53ea\u8f93\u5165 address\uff1a</p>
<pre><code>read -r -p "Paste group URI: " CFLIB_URI
export CFLIB_URI
printf "export CFLIB_URI='%s'\\n" "$CFLIB_URI" &gt;&gt; ~/.bashrc
echo "$CFLIB_URI"</code></pre>
<p>\u8be5\u547d\u4ee4\u5c06\u5b8c\u6574 URI \u4fdd\u5b58\u4e3a <code>CFLIB_URI</code> \u73af\u5883\u53d8\u91cf\uff0c\u4ee5\u540e\u6253\u5f00\u65b0\u7ec8\u7aef\u4e5f\u4f1a\u81ea\u52a8\u751f\u6548\u3002\u540e\u7eed\u5b9e\u9a8c\u4e2d\u7684\u4ee3\u7801\u7edf\u4e00\u901a\u8fc7 <code>uri_helper.uri_from_env()</code> \u8bfb\u53d6\u8be5\u53d8\u91cf\uff0c\u65e0\u9700\u5728\u6bcf\u4e2a\u811a\u672c\u4e2d\u91cd\u590d\u4fee\u6539\u5730\u5740\u3002\u5982\u679c\u7ec4\u522b URI \u53d1\u751f\u53d8\u5316\uff0c\u8bf7\u5728 <code>~/.bashrc</code> \u4e2d\u66f4\u65b0 <code>export CFLIB_URI=...</code> \u8fd9\u4e00\u884c\u3002</p>
<p>\u4e5f\u53ef\u4ee5\u4ec5\u5bf9\u67d0\u4e00\u6b21\u8fd0\u884c\u4e34\u65f6\u6307\u5b9a URI\u3002\u4e0b\u9762\u4ee5 6 \u7ec4\u8fd0\u884c <code>test.py</code> \u4e3a\u4f8b\uff0c\u4f7f\u7528\u65f6\u5fc5\u987b\u66ff\u6362\u4e3a\u672c\u7ec4 URI \u548c\u5b9e\u9645\u811a\u672c\u540d\uff1a</p>
<pre><code>CFLIB_URI='radio://0/60/2M/E7E7E7E7A6' python3 test.py</code></pre>
<div class="admonition warning"><p class="admonition-title">\u8bfe\u5802\u6ce8\u610f\u4e8b\u9879</p><p>\u540c\u4e00\u623f\u95f4\u591a\u7ec4\u5b9e\u9a8c\u65f6\uff0c\u4fe1\u9053\u5c3d\u91cf\u62c9\u5f00\uff0c\u4f8b\u5982\u95f4\u9694 10\uff1b\u6bcf\u67b6\u65e0\u4eba\u673a\u548c\u6bcf\u53f0\u7535\u8111\u65c1\u5e94\u8d34\u4e0a\u7ec4\u522b\u3001channel\u3001address \u548c\u5b8c\u6574 URI\u3002\u6b63\u5f0f\u98de\u884c\u524d\u5148\u9010\u7ec4\u5355\u72ec\u6d4b\u8bd5\u8fde\u63a5\uff0c\u786e\u8ba4\u4e0d\u4f1a\u626b\u63cf\u6216\u8fde\u63a5\u5230\u5176\u4ed6\u7ec4\u65e0\u4eba\u673a\u3002</p></div>
'''
        if "radio://0/120/2M/E7E7E7E7AC" not in body:
            body = body.replace(marker, radio_section + marker)
        return body
    old = f'''<p>Then enter the following command to update the software tool:</p>
<p>pip3 install --upgrade pip setuptools wheel</p>
{image}
<p>Finally, enter the following command to complete the overall software dependency installation:</p>
<pre><code>pip3 install -e .</code></pre>'''
    new = f'''<p>Ubuntu 20.04 uses Python 3.8 by default, so the packaging tools should not be upgraded without version limits. A combination of <code>setuptools 71.x</code> and an older <code>importlib_metadata</code> can cause <code>AttributeError: module &#x27;importlib_metadata&#x27; has no attribute &#x27;EntryPoints&#x27;</code> during the later installation. Newer releases of <code>pip</code> and <code>testresources</code> have also dropped Python 3.8 support. The following command installs a compatible, reproducible set of versions. <code>testresources</code> satisfies a <code>launchpadlib</code> dependency and is separate from the <code>EntryPoints</code> issue.</p>
<pre><code>python3 -m pip install --user --upgrade &quot;pip==24.3.1&quot; &quot;setuptools==70.3.0&quot; &quot;wheel==0.45.1&quot; &quot;importlib-metadata==8.5.0&quot; &quot;testresources==2.0.1&quot;</code></pre>
{image}
<div class="admonition warning"><p class="admonition-title">Troubleshooting</p><p>If you previously ran an unbounded upgrade command and see the <code>EntryPoints</code> error during <code>python3 -m pip install --user -e .</code>, rerun the pinned-version command above. After it succeeds, return to the <code>crazyflie-clients-python</code> directory and continue with the installation command below.</p></div>
<p>Finally, enter the following command to complete the overall software dependency installation:</p>
<pre><code>python3 -m pip install --user -e .</code></pre>'''
    body = body.replace(old, new)
    marker = '<h3>Experiment 4: Use python script to make drone take off autonomously</h3>'
    radio_section = '''<h3>Radio Planning for Multi-group Experiments</h3>
<p>When 12 groups use Crazyradio in the same room, assign each group a fixed complete radio URI. The URI format is <code>radio://interface/channel/data-rate/address</code>, for example <code>radio://0/60/2M/E7E7E7E7A6</code>. The channel reduces same-frequency congestion, while the address prevents accidental connection to another group&apos;s drone. Changing only the address is not enough to fully avoid same-channel interference.</p>
<table><tbody>
<tr><th>Group</th><th>Channel</th><th>Address</th><th>Complete URI</th></tr>
<tr><td>Group 1 / A</td><td>10</td><td><code>E7E7E7E7A1</code></td><td><code>radio://0/10/2M/E7E7E7E7A1</code></td></tr>
<tr><td>Group 2 / B</td><td>20</td><td><code>E7E7E7E7A2</code></td><td><code>radio://0/20/2M/E7E7E7E7A2</code></td></tr>
<tr><td>Group 3 / C</td><td>30</td><td><code>E7E7E7E7A3</code></td><td><code>radio://0/30/2M/E7E7E7E7A3</code></td></tr>
<tr><td>Group 4 / D</td><td>40</td><td><code>E7E7E7E7A4</code></td><td><code>radio://0/40/2M/E7E7E7E7A4</code></td></tr>
<tr><td>Group 5 / E</td><td>50</td><td><code>E7E7E7E7A5</code></td><td><code>radio://0/50/2M/E7E7E7E7A5</code></td></tr>
<tr><td>Group 6 / F</td><td>60</td><td><code>E7E7E7E7A6</code></td><td><code>radio://0/60/2M/E7E7E7E7A6</code></td></tr>
<tr><td>Group 7 / G</td><td>70</td><td><code>E7E7E7E7A7</code></td><td><code>radio://0/70/2M/E7E7E7E7A7</code></td></tr>
<tr><td>Group 8 / H</td><td>80</td><td><code>E7E7E7E7A8</code></td><td><code>radio://0/80/2M/E7E7E7E7A8</code></td></tr>
<tr><td>Group 9 / I</td><td>90</td><td><code>E7E7E7E7A9</code></td><td><code>radio://0/90/2M/E7E7E7E7A9</code></td></tr>
<tr><td>Group 10 / J</td><td>100</td><td><code>E7E7E7E7AA</code></td><td><code>radio://0/100/2M/E7E7E7E7AA</code></td></tr>
<tr><td>Group 11 / K</td><td>110</td><td><code>E7E7E7E7AB</code></td><td><code>radio://0/110/2M/E7E7E7E7AB</code></td></tr>
<tr><td>Group 12 / L</td><td>120</td><td><code>E7E7E7E7AC</code></td><td><code>radio://0/120/2M/E7E7E7E7AC</code></td></tr>
</tbody></table>
<p>To configure a drone, connect one Crazyflie by USB, connect to <code>usb://0</code> in cfclient, open <code>Connect - Configure 2.x</code>, write the assigned Radio channel and Radio address, save the settings, and restart the drone. This changes only the radio configuration stored on the drone; it does not automatically update Python code or the virtual machine.</p>
<h4>Save the Complete URI in the Virtual Machine</h4>
<p>Run the following commands once in each group&apos;s virtual machine. When prompted, copy and paste the group&apos;s complete URI from the table above. Do not enter only the address:</p>
<pre><code>read -r -p "Paste group URI: " CFLIB_URI
export CFLIB_URI
printf "export CFLIB_URI='%s'\\n" "$CFLIB_URI" &gt;&gt; ~/.bashrc
echo "$CFLIB_URI"</code></pre>
<p>The complete URI is stored in the <code>CFLIB_URI</code> environment variable and will be loaded automatically in new terminals. Code in later experiments reads it through <code>uri_helper.uri_from_env()</code>, so the address does not need to be edited in every script. If the assigned URI changes, update the <code>export CFLIB_URI=...</code> line in <code>~/.bashrc</code>.</p>
<p>A URI can also be supplied for one run only. The following example runs <code>test.py</code> for Group 6; replace both the URI and script name before use:</p>
<pre><code>CFLIB_URI='radio://0/60/2M/E7E7E7E7A6' python3 test.py</code></pre>
<div class="admonition warning"><p class="admonition-title">Classroom note</p><p>For multi-group experiments in one room, keep channels well separated, for example by 10 channels. Label each drone and computer with its group, channel, address, and full URI. Before formal flight, test each group one by one and confirm that it does not scan or connect to another group&apos;s drone.</p></div>
'''
    if "Radio Planning for Multi-group Experiments" not in body:
        body = body.replace(marker, radio_section + marker)
    return body


def demo_material_image_src(slug: str, item: dict[str, str], lang: str) -> str:
    image_root = "images-en" if lang == "en" else "images"
    return f"../assets/{image_root}/{slug}/{item['name']}"


def demo_material_section(manual: Manual, lang: str) -> str:
    items = DEMO_MATERIALS.get(manual.slug)
    if not items:
        return ""
    section_meta = {
        "manual-04-multiranger": {
            "zh_heading": "现场测试场地",
            "en_heading": "On-site Test Setup",
            "zh_intro": "本场地用于验证 Multi-ranger 各方向测距读数与挡板相对位置之间的对应关系。",
            "en_intro": "This setup is used to verify the correspondence between Multi-ranger readings and the relative positions of the baffles.",
        },
        "manual-06-complex-map": {
            "zh_heading": "建图结果参考",
            "en_heading": "Mapping Result Reference",
            "zh_intro": "复盘建图实验时，可将现场场地结构与点云输出进行对照，重点检查外边界、内部挡板和异常散点。",
            "en_intro": "When reviewing the mapping experiment, compare the physical arena structure with the point-cloud output, focusing on the outer boundary, internal baffles, and abnormal scattered points.",
        },
        "manual-13-project-demo": {
            "zh_heading": "比赛场地记录",
            "en_heading": "Competition Arena Record",
            "zh_intro": "比赛评价应结合现场飞行、终端日志和影像记录，核对关键通行点与安全边界。",
            "en_intro": "Competition evaluation should combine on-site flight, terminal logs, and visual records to check key passing points and safety boundaries.",
        },
    }
    meta = section_meta.get(manual.slug, {})
    if lang == "zh":
        heading = meta.get("zh_heading", "现场记录")
        intro = meta.get("zh_intro", "")
        title_key = "zh_title"
        text_key = "zh_text"
    else:
        heading = meta.get("en_heading", "On-site Record")
        intro = meta.get("en_intro", "")
        title_key = "en_title"
        text_key = "en_text"
    figures: list[str] = []
    for item in items:
        title = item[title_key]
        description = item[text_key]
        src = demo_material_image_src(manual.slug, item, lang)
        figures.append(
            f'<figure class="demo-figure"><img src="{html.escape(src)}" alt="{html.escape(title)}" loading="lazy" decoding="async">'
            f'<figcaption><strong>{html.escape(title)}</strong><span>{html.escape(description)}</span></figcaption></figure>'
        )
    intro_html = f"<p>{html.escape(intro)}</p>\n" if intro else ""
    heading_html = f"\n<h2>{html.escape(heading)}</h2>\n"
    return heading_html + intro_html + "\n".join(figures)

def demo_video_src(slug: str, item: dict[str, str]) -> str:
    return f"../assets/videos/{slug}/{item['name']}"


def demo_video_section(manual: Manual, lang: str) -> str:
    items = DEMO_VIDEOS.get(manual.slug)
    if not items:
        return ""
    section_meta = {
        "manual-05-ranging": {
            "zh_heading": "飞行记录参考",
            "en_heading": "Flight Record Reference",
            "zh_intro": "复盘测距进阶实验时，应将飞行动作、测距阈值和安全边界一并核对。",
            "en_intro": "When reviewing the advanced ranging experiment, check flight actions, ranging thresholds, and safety boundaries together.",
        },
        "manual-06-complex-map": {
            "zh_heading": "飞行过程记录",
            "en_heading": "Flight Process Record",
            "zh_intro": "飞行视频用于记录采样路径与障碍关系，便于与建图结果交叉核验。",
            "en_intro": "The flight video records the relationship between the sampling path and obstacles, so it can be cross-checked with the mapping result.",
        },
        "manual-11-integrated-practice": {
            "zh_heading": "竞速测试实验记录",
            "en_heading": "Speed Trial Experiment Record",
            "zh_intro": "该视频用于记录阶段综合实践中的竞速路线测试，重点核对通道通过、转向稳定性、速度控制和安全边界。",
            "en_intro": "This video records the speed-trial route test in the integrated practice, focusing on corridor traversal, turning stability, speed control, and safety boundaries.",
        },
        "manual-13-project-demo": {
            "zh_heading": "综合任务飞行记录",
            "en_heading": "Integrated-task Flight Record",
            "zh_intro": "视频记录用于核对路线完成情况、安全边界和评分依据。",
            "en_intro": "The video record is used to check route completion, safety boundaries, and scoring evidence.",
        },
    }
    meta = section_meta.get(manual.slug, {})
    if lang == "zh":
        heading = meta.get("zh_heading", "飞行记录")
        intro = meta.get("zh_intro", "")
        title_key = "zh_title"
        text_key = "zh_text"
    else:
        heading = meta.get("en_heading", "Flight Record")
        intro = meta.get("en_intro", "")
        title_key = "en_title"
        text_key = "en_text"
    figures: list[str] = []
    for item in items:
        title = item[title_key]
        description = item[text_key]
        src = demo_video_src(manual.slug, item)
        figures.append(
            f'<figure class="demo-video"><video controls muted playsinline preload="metadata">'
            f'<source src="{html.escape(src)}" type="video/mp4"></video>'
            f'<figcaption><strong>{html.escape(title)}</strong><span>{html.escape(description)}</span></figcaption></figure>'
        )
    intro_html = f"<p>{html.escape(intro)}</p>\n" if intro else ""
    heading_html = f"\n<h2>{html.escape(heading)}</h2>\n"
    return heading_html + intro_html + "\n".join(figures)


def final_test_image_src(lang: str) -> str:
    image_root = "images-en" if lang == "en" else "images"
    return f"../assets/{image_root}/{FINAL_TEST_SLUG}/{FINAL_TEST_IMAGE_NAME}"


def final_project_demo_body(manual: Manual, lang: str) -> str:
    if lang == "zh":
        image_src = final_test_image_src("zh")
        return f"""
<h1>实验 {manual.number}: {html.escape(manual.zh_title)}</h1>
<p class="subtitle">{html.escape(manual.en_title)}</p>
<h2>最后综合测试</h2>
<p>本实验最终评价仅设置一项综合测试任务。无人机以 0.3 m/s 的固定速度飞行，从 A 区域内任意位置起飞，飞行过程中需要经过 B 点和 C 点，经过 B、C 的顺序不限，最终降落回 A 区域内。</p>
<figure class="wide-figure"><img src="{html.escape(image_src)}" alt="最后综合测试地图与评分规则" loading="lazy" decoding="async"></figure>
<h3>场地约束</h3>
<ul>
<li>挡板位置不一定固定，教师可根据测试批次调整挡板布置，现场以实际摆放为准。</li>
<li>奖励点和起止点是固定的：R1、R2、R3、R4 的位置固定；起止区域固定为 A 区域。</li>
<li>程序不应只硬编码图中挡板坐标，应结合传感器数据、现场观测或规划策略完成避障与路径调整。</li>
</ul>
<h3>评分规则</h3>
<ul>
<li>最终成绩：S = v &times; t - Reward + Punish，成绩值越小越优。</li>
<li>Reward：R1、R2、R3 的奖励值均为 2 m，R4 的奖励值为 5 m。</li>
<li>Punish：最终降落在 A 区时位置不规范，惩罚 0.35 m；未经过 B 点或 C 点，单点惩罚 10 m；最终未回归 A 区，惩罚 20 m。</li>
<li>可使用传感器包括光流测速测高模块和水平测距传感器。</li>
</ul>
<h3>展示要求</h3>
<ul>
<li>展示前应向教师说明代码逻辑、速度设置、传感器使用方式和急停方案。</li>
<li>飞行过程中需保持一名同学负责终端控制和急停，另一名同学记录完整飞行过程。</li>
<li>若无人机接触挡板、姿态明显异常或进入不安全状态，应立即终止程序。</li>
</ul>
"""
    image_src = final_test_image_src("en")
    return f"""
<h1>Experiment {manual.number}: {html.escape(manual.en_title)}</h1>
<h2>Final Comprehensive Test</h2>
<p>The final assessment contains one comprehensive task only. The drone flies at a constant speed of 0.3 m/s, takes off from any position inside Area A, passes through points B and C in any order, and finally lands back inside Area A.</p>
<figure class="wide-figure"><img src="{html.escape(image_src)}" alt="Final comprehensive test map and scoring rules" loading="lazy" decoding="async"></figure>
<h3>Arena Constraints</h3>
<ul>
<li>Baffle positions are not necessarily fixed; the instructor may adjust the baffle layout between test runs, and the on-site setup is authoritative.</li>
<li>The reward points and start/end points are fixed: R1, R2, R3, and R4 keep their positions, and the start/end area is fixed as Area A.</li>
<li>The program should not only hard-code the baffle coordinates shown in the diagram. It should use sensor data, on-site observation, or planning logic to avoid obstacles and adjust the route.</li>
</ul>
<h3>Scoring Rules</h3>
<ul>
<li>Final score: S = v &times; t - Reward + Punish. A lower score is better.</li>
<li>Reward: R1, R2, and R3 are worth 2 m each; R4 is worth 5 m.</li>
<li>Punish: a non-standard final landing in Area A adds 0.35 m; missing point B or C adds 10 m per point; failing to return to Area A adds 20 m.</li>
<li>Available sensors include the Flow deck for velocity and height measurement and the horizontal range sensor.</li>
</ul>
<h3>Demonstration Requirements</h3>
<ul>
<li>Before the demonstration, explain the code logic, speed setting, sensor usage, and emergency-stop plan to the instructor.</li>
<li>During flight, one student should monitor the terminal and emergency stop, while another student records the full flight process.</li>
<li>If the drone touches a baffle, shows abnormal attitude, or enters an unsafe state, stop the program immediately.</li>
</ul>
"""


def write_pages() -> dict[str, dict[str, int]]:
    manifest: dict[str, dict[str, int]] = {}
    extracted: dict[str, tuple[Manual, list[Block], dict[str, int]]] = {}
    translation_texts: set[str] = set()
    for manual in MANUALS:
        blocks, stats = extract_manual(manual)
        extracted[manual.slug] = (manual, blocks, stats)
        manifest[manual.slug] = {**stats, "videos": 0}
        translation_texts.update(collect_translation_texts(blocks))

    image_ocr = collect_image_ocr(extracted)
    translation_texts.update(collect_image_translation_texts(image_ocr))
    cache = ensure_translations(translation_texts)
    image_map = build_english_images(image_ocr, cache)
    copy_final_test_images()
    copy_cfclient_toolchain_image()
    copy_demo_material_images()
    copy_demo_videos()
    for slug, items in DEMO_MATERIALS.items():
        if slug in manifest:
            manifest[slug]["images"] += len(items)
    for slug, items in DEMO_VIDEOS.items():
        if slug in manifest:
            manifest[slug]["videos"] += len(items)

    for manual, blocks, _stats in extracted.values():
        if manual.slug == FINAL_TEST_SLUG:
            zh_body = '<h1>\u6bd4\u8d5b\u8bf4\u660e\uff1a\u7efc\u5408\u9879\u76ee\u5c55\u793a\u4efb\u52a1</h1><p class="subtitle">Integrated Project Competition</p>' + render_blocks(blocks, "zh", cache)
            en_body = '<h1>Competition Brief: Integrated Project Competition</h1>' + render_blocks(blocks, "en", cache, image_map)
        else:
            zh_body = f'<h1>\u5b9e\u9a8c {manual.number}: {html.escape(manual.zh_title)}</h1><p class="subtitle">{html.escape(manual.en_title)}</p>' + render_blocks(blocks, "zh", cache)
            en_body = english_body(manual, blocks, cache, image_map)
        zh_body = apply_course_material_overrides(manual, "zh", zh_body)
        en_body = apply_course_material_overrides(manual, "en", en_body)
        zh_body = apply_manual_overrides(manual, "zh", zh_body)
        en_body = apply_manual_overrides(manual, "en", en_body)
        zh_body = apply_flight_code_safety_overrides(manual, "zh", zh_body)
        en_body = apply_flight_code_safety_overrides(manual, "en", en_body)
        zh_body = apply_group_uri_overrides(manual, "zh", zh_body)
        en_body = apply_group_uri_overrides(manual, "en", en_body)
        zh_body = apply_course_material_overrides(manual, "zh", zh_body)
        en_body = apply_course_material_overrides(manual, "en", en_body)
        zh_body += demo_material_section(manual, "zh")
        en_body += demo_material_section(manual, "en")
        zh_body += demo_video_section(manual, "zh")
        en_body += demo_video_section(manual, "en")
        (ROOT / "zh" / f"{manual.slug}.html").write_text(layout("zh", manual.zh_title, zh_body, manual.slug), encoding="utf-8")
        (ROOT / "en" / f"{manual.slug}.html").write_text(layout("en", manual.en_title, en_body, manual.slug), encoding="utf-8")
    return manifest


def write_assets() -> None:
    (ASSET_DIR / "style.css").write_text(STYLE, encoding="utf-8")
    (ASSET_DIR / "site.js").write_text(SCRIPT, encoding="utf-8")


STYLE = """
:root{--sidebar:#343131;--sidebar-dark:#2a2727;--sidebar-link:#d9d9d9;--accent:#2980b9;--accent-dark:#1f5f8b;--text:#30343b;--muted:#68717d;--border:#dfe5ea;--code:#f5f7f9;--paper:#fff}
*{box-sizing:border-box}
html{font-size:16px}
body{margin:0;color:var(--text);background:#edf0f2;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC","Microsoft YaHei",Arial,sans-serif;font-size:16px;line-height:1.72;letter-spacing:0}
a{color:var(--accent);text-decoration:none}
a:hover{color:var(--accent-dark);text-decoration:underline}
.wy-nav-side{position:fixed;inset:0 auto 0 0;width:300px;overflow:hidden;background:var(--sidebar);color:var(--sidebar-link)}
.wy-side-scroll{height:100%;overflow-y:auto}
.wy-side-nav-search{background:var(--accent);color:#fff;padding:24px 18px 18px;text-align:center}
.icon-home{display:block;color:#fff;font-size:20px;font-weight:700;line-height:1.25}
.icon-home:hover{color:#fff}
.version{margin:8px 0 16px;font-size:13px;opacity:.85}
#doc-search{width:100%;height:36px;border:0;border-radius:4px;padding:0 10px;color:#333}
.wy-menu{padding:16px 0 32px}
.caption{margin:0;padding:0 20px 8px;color:#55a5d9;font-size:12px;font-weight:700;text-transform:uppercase}
.wy-menu ul{list-style:none;padding:0;margin:0}
.wy-menu a{display:block;color:var(--sidebar-link);padding:10px 20px;border-left:4px solid transparent;font-size:14px;line-height:1.4}
.wy-menu a span{display:block;color:#9db9c9;font-size:12px;margin-bottom:2px}
.nav-group{margin:16px 20px 6px;color:#55a5d9;font-size:12px;font-weight:700;text-transform:uppercase}
.wy-menu a.active,.wy-menu a:hover{background:var(--sidebar-dark);border-left-color:var(--accent);color:#fff;text-decoration:none}
.wy-nav-content-wrap{margin-left:300px;min-height:100vh}
.wy-nav-content{background:#fcfcfc;min-height:100vh;padding:38px 56px 88px}
.rst-content{max-width:860px;margin:0 auto}
.breadcrumbs{position:relative;color:var(--muted);font-size:14px;border-bottom:1px solid var(--border);padding-bottom:12px;margin-bottom:18px}
.breadcrumbs span{margin:0 6px}
.github-link{float:right}
.language-switch{display:flex;gap:16px;align-items:center;justify-content:space-between;min-height:54px;margin:0 0 10px;font-size:14px}
.language-options{display:flex;flex:0 0 auto;gap:8px;align-items:center}
.language-options span,.language-options a{border:1px solid var(--border);border-radius:4px;padding:4px 9px}
.language-options span{background:#f3f6f6;color:#555}
.page-affiliation{display:flex;align-items:center;min-width:0;gap:10px;text-align:left}
.page-affiliation img{display:block;flex:0 0 48px;width:48px;height:48px;object-fit:contain}
.page-affiliation-copy{min-width:0;line-height:1.22}
.page-affiliation-copy strong,.page-affiliation-copy small{display:block;letter-spacing:0}
.page-affiliation-copy strong{color:#27323b;font-size:14px;font-weight:750}
.page-affiliation-copy small{margin-top:3px;color:var(--muted);font-size:11px}
h1,h2,h3{color:#1f2328;font-family:inherit;font-weight:650;line-height:1.32;letter-spacing:0}
h1{font-size:32px;margin:22px 0 12px}
h2{font-size:24px;margin:42px 0 18px;padding:0 0 9px;border-bottom:1px solid var(--border)}
h3{font-size:18px;margin:28px 0 10px;color:#303846;font-weight:650}
h2+h3{margin-top:8px}
.subtitle{color:var(--muted);font-size:16px;margin:-4px 0 28px}
p{margin:0 0 15px}
p+figure,ul+figure,ol+figure,pre+figure{margin-top:24px}
ul,ol{padding-left:1.45rem;margin:10px 0 18px}
li{margin:7px 0;padding-left:2px}
.numbered-list{padding-left:1.55rem}
code{background:var(--code);border:1px solid #d6dde3;border-radius:4px;padding:1px 5px;font-family:Consolas,"SFMono-Regular","Cascadia Mono","Liberation Mono",monospace;font-size:.92em}
pre{background:var(--code);border:1px solid #d6dde3;border-radius:6px;overflow-x:auto;overflow-y:visible;padding:16px 18px;margin:18px 0 24px;line-height:1.55}
pre.has-copy-button{position:relative;padding-top:48px}
pre code{display:block;border:0;padding:0;background:transparent;font-size:14px;white-space:pre}
.copy-code{position:absolute;top:9px;right:10px;border:1px solid #b9c4cc;border-radius:4px;background:#fff;color:#33404a;padding:4px 10px;font:600 12px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;cursor:pointer}
.copy-code:hover{border-color:var(--accent);color:var(--accent-dark)}
.copy-code:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
table{width:100%;border-collapse:collapse;margin:18px 0 24px;background:var(--paper);font-size:15px}
td,th{border:1px solid var(--border);padding:9px 11px;vertical-align:top}
figure{margin:24px 0 30px;text-align:center;overflow-x:auto}
figure img{display:block;width:auto;height:auto;max-width:100%;max-height:76vh;object-fit:contain;margin:0 auto;background:var(--paper);border:1px solid var(--border);border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.demo-figure{max-width:720px;margin:22px auto 28px}
.demo-figure img{max-width:100%;max-height:62vh}
.demo-figure figcaption{max-width:680px;margin:10px auto 0;color:var(--muted);font-size:14px;line-height:1.55;text-align:left}
.demo-figure figcaption strong{display:block;color:#2b333c;font-size:15px;margin-bottom:3px}
.demo-figure figcaption span{display:block}
.demo-video{max-width:720px;margin:22px auto 28px}
.demo-video video{display:block;width:100%;max-height:62vh;background:#111;border:1px solid var(--border);border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.demo-video figcaption{max-width:680px;margin:10px auto 0;color:var(--muted);font-size:14px;line-height:1.55;text-align:left}
.demo-video figcaption strong{display:block;color:#2b333c;font-size:15px;margin-bottom:3px}
.demo-video figcaption span{display:block}
.admonition{border-left:4px solid var(--accent);background:#eef7fc;padding:12px 16px;margin:18px 0}
.admonition.warning{border-left-color:#c45f18;background:#fff5eb}
.admonition-title{font-weight:700;margin-bottom:6px}
.toctree-wrapper{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin-top:16px}
.doc-card{display:block;background:#fff;border:1px solid var(--border);border-radius:6px;padding:14px 16px}
.doc-card:hover{text-decoration:none;border-color:var(--accent)}
.doc-card span{display:inline-block;color:#fff;background:var(--accent);border-radius:3px;padding:1px 6px;font-size:12px;margin-bottom:8px}
.doc-card strong{display:block;color:#222}
.doc-card em{display:block;color:var(--muted);font-style:normal;font-size:14px}
.step{padding-left:12px;border-left:3px solid #d9e8f2;color:#36414d}
.manual-credit{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin-top:56px;padding-top:18px;border-top:1px solid var(--border);color:var(--muted);font-size:13px;line-height:1.55}
.manual-credit strong{display:block;color:#333b44;font-size:14px}
.manual-credit span{display:block}
.manual-credit a{white-space:nowrap}
.mobile-bar{display:none;align-items:center;gap:12px;background:var(--sidebar);color:#fff;padding:10px 14px}
#menu-toggle{appearance:none;border:1px solid rgba(255,255,255,.35);background:transparent;color:#fff;border-radius:4px;width:34px;height:32px;font-size:20px}
.hidden-by-search{display:none!important}
@media(max-width:900px){
  .wy-nav-side{transform:translateX(-100%);transition:transform .2s ease;z-index:10}
  body.nav-open .wy-nav-side{transform:translateX(0)}
  .wy-nav-content-wrap{margin-left:0}
  .mobile-bar{display:flex;position:sticky;top:0;z-index:5}
  .wy-nav-content{padding:24px 20px 64px}
  .rst-content{max-width:100%}
  figure{margin:18px 0}
  figure img{max-width:100%;max-height:none}
  h1{font-size:28px}
  h2{font-size:22px;margin-top:34px}
  h3{font-size:18px}
  .github-link{float:none;display:block;margin-top:8px}
  .language-switch{gap:10px;min-height:46px}
  .page-affiliation{gap:7px}
  .page-affiliation img{flex-basis:40px;width:40px;height:40px}
  .page-affiliation-copy strong{font-size:12px}
  .page-affiliation-copy small{font-size:10px}
  .manual-credit{align-items:flex-start;flex-direction:column;gap:8px;margin-top:42px}
}
""".strip() + "\n"

SCRIPT = """
const toggle = document.getElementById('menu-toggle');
if (toggle) {
  toggle.addEventListener('click', () => document.body.classList.toggle('nav-open'));
}

const search = document.getElementById('doc-search');
const navItems = Array.from(document.querySelectorAll('#nav-list li'));
if (search) {
  search.addEventListener('input', () => {
    const query = search.value.trim().toLowerCase();
    navItems.forEach((item) => {
      const text = item.textContent.toLowerCase();
      item.classList.toggle('hidden-by-search', query && !text.includes(query));
    });
  });
}

const isZh = document.documentElement.lang.toLowerCase().startsWith('zh');
const languageSwitch = document.querySelector('.language-switch');
if (languageSwitch && !languageSwitch.querySelector('.page-affiliation')) {
  const options = document.createElement('div');
  options.className = 'language-options';
  Array.from(languageSwitch.children).forEach((child) => options.appendChild(child));

  const affiliation = document.createElement('div');
  affiliation.className = 'page-affiliation';
  const emblem = document.createElement('img');
  emblem.src = '../assets/images/beihang-university-emblem.png';
  emblem.alt = isZh ? '北京航空航天大学校徽' : 'Beihang University emblem';
  emblem.width = 48;
  emblem.height = 48;

  const copy = document.createElement('span');
  copy.className = 'page-affiliation-copy';
  const groupName = document.createElement('strong');
  groupName.textContent = 'ADMIRE Group';
  const university = document.createElement('small');
  university.textContent = isZh ? '北京航空航天大学' : 'Beihang University';
  copy.append(groupName, university);
  affiliation.append(emblem, copy);
  languageSwitch.append(affiliation, options);
}

const content = document.querySelector('.rst-content');
if (content && !content.querySelector('.manual-credit')) {
  const footer = document.createElement('footer');
  footer.className = 'manual-credit';

  const affiliation = document.createElement('div');
  const affiliationName = document.createElement('strong');
  affiliationName.textContent = isZh ? '北航 ADMIRE 组' : 'BUAA ADMIRE Group';
  const affiliationDetail = document.createElement('span');
  affiliationDetail.textContent = isZh ? '北京航空航天大学' : 'Beihang University';
  affiliation.append(affiliationName, affiliationDetail);

  const author = document.createElement('div');
  const authorName = document.createElement('span');
  authorName.textContent = isZh ? '编写者：楼嘉彬' : 'Author: Lou Jiabin';
  const email = document.createElement('a');
  email.href = 'mailto:loujiabin@buaa.edu.cn';
  email.textContent = 'loujiabin@buaa.edu.cn';
  author.append(authorName, email);
  footer.append(affiliation, author);
  content.appendChild(footer);
}

document.querySelectorAll('pre code').forEach((code) => {
  const pre = code.parentElement;
  if (!pre || pre.querySelector('.copy-code')) return;
  pre.classList.add('has-copy-button');
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'copy-code';
  button.textContent = isZh ? '复制' : 'Copy';
  button.setAttribute('aria-label', isZh ? '复制代码' : 'Copy code');
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(code.textContent);
      button.textContent = isZh ? '已复制' : 'Copied';
    } catch (error) {
      const range = document.createRange();
      range.selectNodeContents(code);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      button.textContent = isZh ? '请按 Ctrl+C' : 'Press Ctrl+C';
    }
    setTimeout(() => {
      button.textContent = isZh ? '复制' : 'Copy';
    }, 1600);
  });
  pre.appendChild(button);
});
""".strip() + "\n"


def write_root_files(manifest: dict[str, dict[str, int]]) -> None:
    (ROOT / "index.html").write_text('<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=en/index.html"><title>Palm-sized UAV Autonomous Systems Laboratory Manual</title><link rel="icon" type="image/svg+xml" href="assets/favicon.svg?v=2"></head><body><p><a href="en/index.html">English</a> &middot; <a href="zh/index.html">Chinese</a></p></body></html>\n', encoding="utf-8")
    (ROOT / ".nojekyll").write_text("", encoding="utf-8")
    (ROOT / "docs-manifest.json").write_text(json.dumps({"source_dir": str(SOURCE_DIR), "manuals": [manual.__dict__ for manual in MANUALS], "stats": manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "README.md").write_text("""# Palm-sized UAV Autonomous Systems Laboratory Manual

Bilingual experiment manual for palm-sized UAV summer school labs.

- The GitHub Pages root entry opens the English documentation by default.
- `zh/` contains Chinese experiment pages, including text, tables, links, commands, and figures.
- `en/` contains English experiment pages with language switches back to the Chinese pages.
- `.github/workflows/pages.yml` deploys the static site with GitHub Pages Actions.

## Course Materials

Download the `course-materials` folder from the [BUAA cloud link](https://bhpan.buaa.edu.cn/link/AA5DF49653676B4EDFBAB8B2A09B0FBEE9). The link is valid until 2028-11-11 10:31.

## Local preview

Open `index.html` in a browser, or serve this directory with any static file server.

## Maintenance

```bash
python tools/build_objective_docs.py
```
""", encoding="utf-8")
    workflow = ROOT / ".github" / "workflows"
    workflow.mkdir(parents=True, exist_ok=True)
    (workflow / "pages.yml").write_text("""name: Deploy documentation to GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Configure Pages
        uses: actions/configure-pages@v5
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: .
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
""", encoding="utf-8")


def main() -> None:
    clean_output()
    write_assets()
    manifest = write_pages()
    write_index("zh")
    write_index("en")
    write_root_files(manifest)
    image_count = sum(item["images"] for item in manifest.values())
    video_count = sum(item.get("videos", 0) for item in manifest.values())
    print(f"Built {len(MANUALS)} objective manuals with {image_count} images and {video_count} videos.")


if __name__ == "__main__":
    main()
