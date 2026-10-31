"""Hand explicit method outputs back to the local workbench.

WorkBuddy and Codex both use this entry. It calls the same publisher as
assets/workbench/workbuddy_publish_method.py.
"""
import argparse, json, sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / 'assets' / 'workbench'
sys.path.insert(0, str(APP))
from workbuddy_publish_method import publish

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(publish(args.manifest), ensure_ascii=False))
    except (ValueError, KeyError, OSError) as error:
        raise SystemExit(str(error))

if __name__ == '__main__':
    main()
