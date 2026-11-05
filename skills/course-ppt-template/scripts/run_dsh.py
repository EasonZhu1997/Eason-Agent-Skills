#!/usr/bin/env python3
"""Run the installed DSH headless CLI against this course PPT skill.

Uses DSH's existing account login without copying or printing credentials.
The model selector is exact: there is deliberately no model fallback.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import uuid


BUNDLED_DSH = Path(
    "/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh"
)


def cli_path(explicit: str | None) -> Path:
    candidate = explicit or shutil.which("dsh")
    path = Path(candidate).expanduser() if candidate else BUNDLED_DSH
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("DSH CLI not found; pass --dsh-cli /absolute/path/to/dsh")
    return path.resolve()


def execute(command: list[str], cwd: Path, work: Path, timeout: float,
            stem: str, stdin: str | None = None) -> int:
    """Keep child logs private and terminate its process group on timeout."""
    with (work / f"{stem}.stdout.jsonl").open("w", encoding="utf-8") as out, \
            (work / f"{stem}.stderr.log").open("w", encoding="utf-8") as err:
        child = subprocess.Popen(
            command, cwd=cwd, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=out, stderr=err, text=True, encoding="utf-8", start_new_session=True,
        )
        try:
            child.communicate(input=stdin, timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
            raise
        return child.returncode


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", required=True, type=Path,
                        help="UTF-8 course brief file")
    parser.add_argument("--output", required=True, type=Path,
                        help="New .pptx output path; existing files are not overwritten")
    parser.add_argument("--template", type=Path,
                        default=Path.home() / ".dsh/course-ppt-template/template.pptx")
    parser.add_argument("--model", default="deepseek-flash",
                        help="Exact DSH account model ID (default: deepseek-flash)")
    parser.add_argument("--timeout", type=float, default=1200,
                        help="Headless run time limit in seconds (default: 1200)")
    parser.add_argument("--dsh-cli", help="DSH CLI executable; auto-detects app-bundled CLI")
    parser.add_argument("--dry-run", action="store_true",
                        help="Prepare private prompt/patch and print command without inference")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    skill = Path(__file__).resolve().parent.parent
    brief = args.brief.expanduser().resolve()
    output = args.output.expanduser().resolve()
    template = args.template.expanduser().resolve()
    profile = skill / "references/profile.json"
    engine = skill / "scripts/pptx_engine.py"
    if not brief.is_file():
        raise ValueError(f"Brief does not exist: {brief}")
    brief.read_text(encoding="utf-8")  # Fail before starting paid inference on invalid input.
    if not template.is_file():
        raise ValueError(f"Template does not exist: {template}; run the skill bootstrap first")
    if not args.model.strip() or args.timeout <= 0:
        raise ValueError("--model must be nonempty and --timeout must be positive")
    if output.suffix.lower() != ".pptx":
        raise ValueError("--output must end in .pptx")
    if output.exists():
        raise ValueError(f"Output already exists; choose a new path: {output}")
    for required in (skill / "SKILL.md", profile, engine):
        if not required.is_file():
            raise ValueError(f"Skill resource missing: {required}")
    dsh = cli_path(args.dsh_cli)
    output.parent.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work = output.parent / ".work" / f"dsh-{stamp}-{uuid.uuid4().hex[:8]}"
    work.mkdir(parents=True, mode=0o700)
    work.chmod(0o700)
    content = work / "content.json"
    patch = work / "headless.patch.json"
    entries = [
        {"id": "authorization", "disabled": False},
        {"id": "credentials", "disabled": False},
        {"id": "deepseek-account", "disabled": False},
        {"id": "agent-default-model", "config": {
            "provider": "deepseek-account", "model": args.model, "reasoningEffort": "high",
        }},
        {"id": "skill-filesystem", "config": {
            "includeDefaultRoots": False, "customSkillDirs": [str(skill.parent)], "watch": False,
        }},
        {"id": "session-title-llm", "disabled": True},
        {"id": "session-telemetry-otel", "disabled": True},
        {"id": "otel", "disabled": True},
    ]
    patch.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    build = [sys.executable, str(engine), "build", "--template", str(template),
             "--profile", str(profile), "--content", str(content), "--output", str(output)]
    validate = [sys.executable, str(engine), "validate", "--pptx", str(output),
                "--profile", str(profile), "--content", str(content), "--template", str(template)]
    prompt = f"""请使用本机 course-ppt-template skill 完成一次真实课件生成。
先通过原生 skill 工具加载 course-ppt-template；若未列出，用 read 读取 {skill / 'SKILL.md'}。
只读取本次 skill、模板、profile 和课程简报。不要读取凭据、账号、其他聊天或修改 DSH 配置。
课程简报文件：{brief}
模板文件：{template}
版式契约：{profile}
内容输出：{content}
PPT 输出：{output}

请读取课程简报和 profile，完成课程教学内容。严格使用 profile 内的 layout 和语义槽位。
写一个 UTF-8 JSON 对象到内容输出路径：{{"title":"课程名","slides":[{{"layout":"cover","slots":{{"title":"标题"}}}}]}}。
该例只说明根结构。实际每页必须遵守 profile：提供该版式全部非 auto 槽位，不要写 auto 槽位，遵守 max_chars 和 max_lines。
不要把实现、验证过程写进教学内容。遇到文字过长先缩写或拆页，禁止改字体字号、位置、背景和模板。
然后用 bash 执行下列 argv 对应的命令（正确引用每个参数）：
build argv: {json.dumps(build, ensure_ascii=False)}
validate argv: {json.dumps(validate, ensure_ascii=False)}
如校验失败，只修订 content.json 再运行 build 和 validate，最多修订 3 次。
只使用指定模型 {args.model}。禁止切换模型、修改源 skill 或引擎，不要启动子代理、后台任务或 goal。
文件已获用户授权在当前输出目录新建。不要替换已有其他文件。
只有 build 和 validate 均成功，才报告 PPT 生成成功。最终回复给出输出绝对路径及验证结果。
"""
    (work / "prompt.txt").write_text(prompt, encoding="utf-8")
    command = [str(dsh), "headless", "--patch", str(patch), "--json", "-"]
    metadata = {
        "provider": "deepseek-account", "model": args.model, "dsh_cli": str(dsh),
        "brief": str(brief), "template": str(template), "skill": str(skill),
        "output": str(output), "content": str(content), "command": command,
    }
    (work / "run.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
    print(f"Exact model: deepseek-account/{args.model}", flush=True)
    print(f"Private run records: {work}", flush=True)
    if args.dry_run:
        print(json.dumps(command, ensure_ascii=False))
        return 0
    result = execute(command, output.parent, work, args.timeout, "dsh", stdin=prompt)
    metadata["dsh_exit_code"] = result
    failed_turn = False
    session_id = None
    for line in (work / "dsh.stdout.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "session":
            session_id = event.get("sessionId")
        if event.get("type") == "status" and event.get("phase") == "turn_end":
            failed_turn |= event.get("reason", {}).get("kind") != "completed"
    metadata["session_id"] = session_id
    metadata["dsh_failed_turn"] = failed_turn
    metadata["independent_validate_exit_code"] = None
    if result == 0 and not failed_turn and output.is_file() and content.is_file():
        metadata["independent_validate_exit_code"] = execute(
            validate, output.parent, work, min(args.timeout, 180), "independent-validate")
    success = metadata["independent_validate_exit_code"] == 0
    metadata["status"] = "passed" if success else "failed"
    (work / "run.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
    if not success:
        print(f"Generation did not pass; inspect private records at {work}", file=sys.stderr)
        return result if result != 0 else 1
    print(f"PPTX generated and independently validated: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"run_dsh: {exc}", file=sys.stderr)
        raise SystemExit(1)
