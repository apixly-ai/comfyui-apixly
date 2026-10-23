import assert from "node:assert/strict";
import test from "node:test";
import { nativeDownloadURL, safeResultURL } from "../web/helpers.mjs";

test("result links accept signed HTTPS URLs and reject script/credential URLs", () => {
  assert.equal(safeResultURL("https://media.example/result?ref=signed"), "https://media.example/result?ref=signed");
  for (const value of ["javascript:alert(1)", "http://example.com", "https://user:pass@example.com", "invalid"]) {
    assert.equal(safeResultURL(value), null);
  }
});

test("download controls address only saved ComfyUI output and temporary files", () => {
  const value = nativeDownloadURL({ filename: "image 1.png", subfolder: "apixly", type: "temp" });
  assert.equal(new URL(value, "http://localhost").searchParams.get("filename"), "image 1.png");
  assert.equal(nativeDownloadURL({ filename: "../secret", type: "output" }), null);
  assert.equal(nativeDownloadURL({ filename: "file", type: "input" }), null);
  assert.equal(nativeDownloadURL({ filename: "file", subfolder: "../private", type: "output" }), null);
});
