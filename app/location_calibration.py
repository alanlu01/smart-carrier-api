import argparse
import json
import math

from app import repository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely preview or apply one measured ROS map service-point pose."
    )
    parser.add_argument("code", help="Cloud location code, for example A1")
    parser.add_argument("x", type=float, help="Map-frame X coordinate")
    parser.add_argument("y", type=float, help="Map-frame Y coordinate")
    parser.add_argument("yaw", type=float, help="Map-frame heading in radians")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit the update. Without this flag the command is a dry run.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    values = (args.x, args.y, args.yaw)
    if not all(math.isfinite(value) for value in values):
        parser.error("x, y, and yaw must be finite numbers")

    code = args.code.strip().upper()
    current = repository.get_location(code)
    if current is None:
        parser.error(f"location {code!r} does not exist")

    proposal = {"code": code, "x": args.x, "y": args.y, "yaw": args.yaw}
    print(json.dumps({"current": current, "proposed": proposal}, default=str, ensure_ascii=False))
    if not args.apply:
        print("Dry run only; re-run with --apply after map validation passes.")
        return 0

    try:
        updated = repository.update_location_coordinates(code, args.x, args.y, args.yaw)
    except repository.LocationHasActiveTasks as exc:
        parser.error(str(exc))
    if updated is None:
        parser.error(f"location {code!r} disappeared before update")
    print(json.dumps({"updated": updated}, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
