// Step 2 of the asset pack build: compress the raw inputs into assets-pack/.
//
//   node assets-pack/_build/build.mjs <work dir> <assets-pack dir>
//
// Textures and decals -> KTX2 (Basis Universal): color + decals ETC1S sRGB, roughness ETC1S
// linear, normal maps UASTC linear + zstd, all with mipmaps. Models -> GLB with meshopt
// compression (EXT_meshopt_compression + KHR_mesh_quantization); the person's texture -> KTX2.
// HDRI stays .hdr (RGBELoader). Writes manifest.json and CREDITS.md.
// Needs (npm, in a temp dir): ktx2-encoder sharp @gltf-transform/core @gltf-transform/extensions
// @gltf-transform/functions meshoptimizer  (see README.md).
import { encodeToKTX2 } from "ktx2-encoder";
import { ktx2 } from "ktx2-encoder/gltf-transform";
import sharp from "sharp";
import { NodeIO } from "@gltf-transform/core";
import { ALL_EXTENSIONS } from "@gltf-transform/extensions";
import { reorder, quantize, meshopt, getBounds, prune, dedup } from "@gltf-transform/functions";
import { MeshoptEncoder, MeshoptDecoder } from "meshoptimizer";
import { readFileSync, writeFileSync, mkdirSync, copyFileSync, statSync, readdirSync, rmSync } from "fs";
import { join, dirname, relative } from "path";

const [work, out] = process.argv.slice(2);
const raw = join(work, "raw");
const credits = JSON.parse(readFileSync(join(work, "credits.json"), "utf8"));
const byName = Object.fromEntries(credits.map((c) => [c.name, c]));

const decoder = async (buf) => {
  const { data, info } = await sharp(Buffer.from(buf)).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  return { width: info.width, height: info.height, data: new Uint8Array(data) };
};
const OPTS = {
  color: { isUASTC: false, qualityLevel: 160, isSetKTX2SRGBTransferFunc: true, isPerceptual: true },
  roughness: { isUASTC: false, qualityLevel: 128, isSetKTX2SRGBTransferFunc: false, isPerceptual: false },
  normal: { isUASTC: true, isNormalMap: true, isPerceptual: false, isSetKTX2SRGBTransferFunc: false,
            needSupercompression: true, enableRDO: true, rdoQualityLevel: 1.5 },
  decal: { isUASTC: false, qualityLevel: 180, isSetKTX2SRGBTransferFunc: true, isPerceptual: true },
};

async function toKTX2(src, dst, kind) {
  const buf = await encodeToKTX2(new Uint8Array(readFileSync(src)),
    { imageDecoder: decoder, generateMipmap: true, isKTX2File: true, ...OPTS[kind] });
  mkdirSync(dirname(dst), { recursive: true });
  writeFileSync(dst, buf);
  const meta = await sharp(src).metadata();
  return { width: meta.width, height: meta.height };
}

rmSync(out + "/textures", { recursive: true, force: true });
rmSync(out + "/decals", { recursive: true, force: true });
rmSync(out + "/models", { recursive: true, force: true });
rmSync(out + "/hdri", { recursive: true, force: true });
const entries = [];
const add = (path, extra) => entries.push({ path: relative(out, path).replaceAll("\\", "/"), bytes: statSync(path).size, ...extra });

// textures
for (const c of credits.filter((c) => c.kind === "texture")) {
  for (const slot of ["color", "normal", "roughness"]) {
    const dst = join(out, "textures", c.name, `${c.name}_${slot}.ktx2`);
    const { width, height } = await toKTX2(join(raw, `${c.name}_${slot}.jpg`), dst, slot);
    add(dst, { kind: "texture", set: c.name, map: slot, format: "ktx2", codec: OPTS[slot].isUASTC ? "UASTC+zstd" : "ETC1S",
               colorSpace: slot === "color" ? "srgb" : "linear", width, height, mipmaps: true, credit: c.name });
  }
}
// decals
for (const c of credits.filter((c) => c.kind === "decal")) {
  const dst = join(out, "decals", `${c.name}.ktx2`);
  const { width, height } = await toKTX2(join(raw, `${c.name}.png`), dst, "decal");
  add(dst, { kind: "decal", format: "ktx2", codec: "ETC1S", colorSpace: "srgb", alpha: true, width, height, mipmaps: true, credit: c.name });
}
// HDRI
{
  const dst = join(out, "hdri", "sky_overcast.hdr");
  mkdirSync(dirname(dst), { recursive: true });
  copyFileSync(join(raw, "sky_overcast.hdr"), dst);
  add(dst, { kind: "hdri", format: "hdr", width: 1024, height: 512, credit: "sky_overcast" });
}

// models
await MeshoptEncoder.ready;
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({ "meshopt.encoder": MeshoptEncoder, "meshopt.decoder": MeshoptDecoder });

function triangles(doc) {
  let t = 0;
  for (const m of doc.getRoot().listMeshes()) for (const p of m.listPrimitives()) {
    const i = p.getIndices();
    t += (i ? i.getCount() : p.getAttribute("POSITION").getCount()) / 3;
  }
  return t;
}

async function layPersonDown(doc) {
  // Source: T-pose, Y up, facing +X (toes point +X), arms along Z.
  // -> lying on its back, head toward +X, arms out along Z, origin at floor center.
  const scene = doc.getRoot().listScenes()[0];
  const wrap = doc.createNode("person");
  for (const child of scene.listChildren()) { scene.removeChild(child); wrap.addChild(child); }
  scene.addChild(wrap);
  const s = Math.SQRT1_2;
  // q = Ry(180deg) * Rz(90deg): Rz turns front +X -> +Y (face up) and head +Y -> -X; Ry flips head to +X
  const qz = [0, 0, s, s], qy = [0, 1, 0, 0];
  const mul = (a, b) => [
    a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1],
    a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
    a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3],
    a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2]];
  wrap.setRotation(mul(qy, qz));
  // normalize body length (now along X) to a 1.75 m adult, then move to the floor and center it
  const b0 = getBounds(scene);
  const length = b0.max[0] - b0.min[0];
  const k = 1.75 / length;
  wrap.setScale([k, k, k]);
  const b = getBounds(scene);
  wrap.setTranslation([-(b.min[0] + b.max[0]) / 2, -b.min[1], -(b.min[2] + b.max[2]) / 2]);
}

for (const name of ["robot", "person"]) {
  const src = join(raw, name === "person" ? "person_src.glb" : "robot.glb");
  const doc = await io.read(src);
  if (name === "person") await layPersonDown(doc);
  const tf = [dedup(), prune(), reorder({ encoder: MeshoptEncoder }), quantize(), meshopt({ encoder: MeshoptEncoder, level: "medium" })];
  if (name === "person") tf.unshift(ktx2({ imageDecoder: decoder, isUASTC: false, qualityLevel: 160, generateMipmap: true }));
  await doc.transform(...tf);
  const dst = join(out, "models", `${name}.glb`);
  mkdirSync(dirname(dst), { recursive: true });
  await io.write(dst, doc);
  const b = getBounds(doc.getRoot().listScenes()[0]);
  const size = b.max.map((v, i) => +(v - b.min[i]).toFixed(3));
  add(dst, { kind: "model", format: "glb", compression: "EXT_meshopt_compression + KHR_mesh_quantization",
             triangles: triangles(doc), nodes: doc.getRoot().listNodes().map((n) => n.getName()).filter(Boolean),
             size_m: size, up: "+Y", units: "meters", origin: "floor center", facing: name === "robot" ? "+X" : "lying on its back, head +X",
             textures: doc.getRoot().listTextures().map((t) => t.getMimeType()), credit: name });
}

// manifest + credits
const total = entries.reduce((a, e) => a + e.bytes, 0);
const manifest = {
  name: "Deadzone asset pack", version: 1, total_bytes: total,
  loaders: { ktx2: "three/examples/jsm/loaders/KTX2Loader.js (+ basis transcoder in three/examples/jsm/libs/basis/)",
             glb: "GLTFLoader with setMeshoptDecoder(MeshoptDecoder) and setKTX2Loader(ktx2Loader)",
             hdr: "three/examples/jsm/loaders/RGBELoader.js" },
  conventions: "1 unit = 1 m, Y up, models' origin at floor center; normal maps are OpenGL (+Y) convention",
  files: entries,
  credits,
};
writeFileSync(join(out, "manifest.json"), JSON.stringify(manifest, null, 1));
const rows = credits.map((c) => `| ${c.name} | ${c.kind} | ${c.title} | ${c.author} | ${c.source}${c.url ? ` (${c.url})` : ""} | ${c.license} |`);
writeFileSync(join(out, "CREDITS.md"), [
  "# Asset pack credits and licences", "",
  "Every file is CC0 1.0 (public domain dedication). No attribution is required, but we credit everyone anyway.",
  "Procedural assets were made by `_build/fetch_and_make.py` and are dedicated to the public domain (CC0 1.0) by the Deadzone team.", "",
  "| Asset | Kind | Title | Author | Source | Licence |", "|---|---|---|---|---|---|", ...rows, "",
  "CC0 1.0: https://creativecommons.org/publicdomain/zero/1.0/", ""].join("\n"));
console.log(`wrote ${entries.length} files, ${(total / 1e6).toFixed(1)} MB`);
for (const e of entries) console.log(`${(e.bytes / 1e6).toFixed(2).padStart(6)} MB  ${e.path}${e.triangles ? `  ${e.triangles} tris` : ""}`);
