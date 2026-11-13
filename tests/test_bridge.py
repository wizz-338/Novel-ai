import base64
import io
import json
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import novelai_bridge as n


class BridgeTests(unittest.TestCase):
    def sample(self, **changes):
        v = {"prompt": "quiet anime frame, two teens at a bus stop"}
        v.update(changes)
        return json.dumps(v)

    def test_dry_run_by_default(self):
        scene = n.parse_scene(self.sample())
        self.assertTrue(scene["dry_run"])
        self.assertEqual(n.build_payload(scene)["model"], "nai-diffusion-4-5-full")
        self.assertEqual(n.build_payload(scene)["parameters"]["n_samples"], 1)

    def test_disallow_batch_and_custom_endpoint(self):
        for bad in ({"n_samples": 999}, {"url": "https://example.org"},
                    {"action": "img2img"}, {"model": "other"}):
            with self.assertRaises(n.BridgeError):
                n.parse_scene(self.sample(**bad))

    def test_disallow_large_and_bad_values(self):
        for bad in ({"width": 4096}, {"steps": 300}, {"scale": 12},
                    {"seed": -1}, {"dry_run": "false"}, {"reference": "../secret"}):
            with self.assertRaises(n.BridgeError):
                n.parse_scene(self.sample(**bad))

    def test_no_reference_is_implicitly_public(self):
        scene = n.parse_scene(self.sample(reference="nari"))
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(n.BridgeError):
                n.build_payload(scene, root)

    def test_owner_issue(self):
        with tempfile.TemporaryDirectory() as root:
            event_path = Path(root) / "event.json"
            event_path.write_text(json.dumps({
                "issue": {"title": "[NAI] test scene",
                          "user": {"login": "wizz-338"},
                          "body": self.sample()}
            }), encoding="utf-8")
            with patch.dict(os.environ, {"GITHUB_REPOSITORY_OWNER": "wizz-338",
                                         "GITHUB_ACTOR": "wizz-338"}):
                self.assertTrue(n.scene_from_event(event_path, "issues")["dry_run"])
            with patch.dict(os.environ, {"GITHUB_REPOSITORY_OWNER": "wizz-338",
                                         "GITHUB_ACTOR": "someone-else"}):
                with self.assertRaises(n.BridgeError):
                    n.scene_from_event(event_path, "issues")

    def test_decode_json(self):
        png = b"\x89PNG\r\n\x1a\n" + b"test"
        payload = json.dumps({"images": [{"image": base64.b64encode(png).decode()}]}).encode()
        self.assertEqual(n.decode_image(payload, "application/json"), png)

    def test_decode_zip(self):
        png = b"\x89PNG\r\n\x1a\n" + b"test"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("image_0.png", png)
        self.assertEqual(n.decode_image(buf.getvalue(), "application/zip"), png)

    def test_missing_token_never_makes_request(self):
        with self.assertRaises(n.BridgeError):
            n.generate_once(n.build_payload(n.parse_scene(self.sample())), "")


if __name__ == "__main__":
    unittest.main()
