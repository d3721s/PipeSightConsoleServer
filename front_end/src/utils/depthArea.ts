// Real surface-area measurement on a depth frame.
//
// A depth frame is a regular pixel grid where each pixel holds a distance (Z).
// With the camera's pinhole intrinsics we back-project each pixel to a real 3D
// point (metres): X=(u-cx)*Z/fx, Y=(v-cy)*Z/fy, Z=depth. The area of a rectangle
// is the sum of the true 3D areas of the two triangles per pixel quad, skipping
// triangles that touch a missing depth or span a depth cliff (occlusion edge),
// so the result follows the real (possibly curved) surface without inflation.

// A depth step larger than this (metres) between neighbours is a depth cliff.
export const DEPTH_CLIFF_M = 0.05

export type DepthIntrinsics = { fx: number; fy: number; cx: number; cy: number }

// A depth frame with depth already converted to metres.
export type DepthFrame = {
  width: number
  height: number
  depthM: Float32Array
  intrinsics: DepthIntrinsics
}

export type AreaResult = {
  areaM2: number
  triangles: number
  skipped: number // triangles dropped (invalid depth or depth cliff)
}

function pixelTo3D(
  frame: DepthFrame,
  u: number,
  v: number
): [number, number, number] | null {
  const z = frame.depthM[v * frame.width + u]
  if (!Number.isFinite(z) || z <= 0) return null
  const { fx, fy, cx, cy } = frame.intrinsics
  return [((u - cx) * z) / fx, ((v - cy) * z) / fy, z]
}

function triArea3D(a: number[], b: number[], c: number[]): number {
  // 0.5 * |(b-a) x (c-a)|
  const abx = b[0] - a[0], aby = b[1] - a[1], abz = b[2] - a[2]
  const acx = c[0] - a[0], acy = c[1] - a[1], acz = c[2] - a[2]
  const cx = aby * acz - abz * acy
  const cy = abz * acx - abx * acz
  const cz = abx * acy - aby * acx
  return 0.5 * Math.sqrt(cx * cx + cy * cy + cz * cz)
}

// Sum the real surface area (m²) of the depth pixels inside a rectangle given in
// the depth frame's pixel space. Returns null if intrinsics/size are unusable.
export function measureRectArea(
  frame: DepthFrame,
  x0: number,
  y0: number,
  x1: number,
  y1: number
): AreaResult | null {
  const { width: w, height: h, intrinsics } = frame
  if (!intrinsics || intrinsics.fx === 0 || intrinsics.fy === 0) return null

  const minX = Math.max(0, Math.min(x0, x1))
  const maxX = Math.min(w - 1, Math.max(x0, x1))
  const minY = Math.max(0, Math.min(y0, y1))
  const maxY = Math.min(h - 1, Math.max(y0, y1))
  if (maxX - minX < 1 || maxY - minY < 1) return null

  const d = frame.depthM
  const notCliff = (z1: number, z2: number) => Math.abs(z1 - z2) <= DEPTH_CLIFF_M
  let area = 0
  let triangles = 0
  let skipped = 0

  const addTri = (
    ua: number, va: number, za: number,
    ub: number, vb: number, zb: number,
    uc: number, vc: number, zc: number
  ) => {
    if (za <= 0 || zb <= 0 || zc <= 0) { skipped++; return }
    if (!notCliff(za, zb) || !notCliff(zb, zc) || !notCliff(za, zc)) { skipped++; return }
    const A = pixelTo3D(frame, ua, va)
    const B = pixelTo3D(frame, ub, vb)
    const C = pixelTo3D(frame, uc, vc)
    if (!A || !B || !C) { skipped++; return }
    area += triArea3D(A, B, C)
    triangles++
  }

  // Each pixel quad (TL,TR,BL,BR) -> 2 triangles: TL-TR-BL and TR-BR-BL.
  for (let v = minY; v < maxY; v++) {
    for (let u = minX; u < maxX; u++) {
      const zTL = d[v * w + u]
      const zTR = d[v * w + u + 1]
      const zBL = d[(v + 1) * w + u]
      const zBR = d[(v + 1) * w + u + 1]
      addTri(u, v, zTL, u + 1, v, zTR, u, v + 1, zBL)
      addTri(u + 1, v, zTR, u + 1, v + 1, zBR, u, v + 1, zBL)
    }
  }
  return { areaM2: area, triangles, skipped }
}

export function formatArea(m2: number): string {
  if (m2 < 0.01) return `${(m2 * 1e4).toFixed(1)} cm²`
  return `${m2.toFixed(4)} m²`
}

// --- raw depth blob (matches the bridge's DPT2 payload, minus the magic) -----
// Layout (little-endian): u32 width, u32 height, u32 format(1=u16,2=f32),
// f32 fx, f32 fy, f32 cx, f32 cy, then width*height depth samples.
const RAW_HEADER_BYTES = 28
const RAW_FORMAT_U16 = 1
const RAW_FORMAT_F32 = 2

// Serialize a u16 (mm) depth frame + intrinsics into a compact ArrayBuffer.
export function encodeDepthRaw(
  width: number,
  height: number,
  depthU16Mm: Uint16Array,
  intr: DepthIntrinsics
): ArrayBuffer {
  const buf = new ArrayBuffer(RAW_HEADER_BYTES + depthU16Mm.length * 2)
  const view = new DataView(buf)
  view.setUint32(0, width, true)
  view.setUint32(4, height, true)
  view.setUint32(8, RAW_FORMAT_U16, true)
  view.setFloat32(12, intr.fx, true)
  view.setFloat32(16, intr.fy, true)
  view.setFloat32(20, intr.cx, true)
  view.setFloat32(24, intr.cy, true)
  new Uint16Array(buf, RAW_HEADER_BYTES).set(depthU16Mm)
  return buf
}

// Parse a raw depth blob (as saved by encodeDepthRaw) into a metres DepthFrame.
export function decodeDepthRaw(buf: ArrayBuffer): DepthFrame | null {
  if (buf.byteLength < RAW_HEADER_BYTES) return null
  const view = new DataView(buf)
  const width = view.getUint32(0, true)
  const height = view.getUint32(4, true)
  const format = view.getUint32(8, true)
  const fx = view.getFloat32(12, true)
  const fy = view.getFloat32(16, true)
  const cx = view.getFloat32(20, true)
  const cy = view.getFloat32(24, true)
  if (!width || !height) return null

  const pixelCount = width * height
  const bytesPerPixel = format === RAW_FORMAT_U16 ? 2 : format === RAW_FORMAT_F32 ? 4 : 0
  if (!bytesPerPixel || buf.byteLength < RAW_HEADER_BYTES + pixelCount * bytesPerPixel) return null

  const depthM = new Float32Array(pixelCount)
  if (format === RAW_FORMAT_U16) {
    const src = new Uint16Array(buf, RAW_HEADER_BYTES, pixelCount)
    for (let i = 0; i < pixelCount; i++) depthM[i] = src[i] * 0.001
  } else {
    const src = new Float32Array(buf, RAW_HEADER_BYTES, pixelCount)
    for (let i = 0; i < pixelCount; i++) {
      const z = src[i]
      depthM[i] = !Number.isFinite(z) || z <= 0 ? 0 : z > 20 ? z * 0.001 : z
    }
  }
  return { width, height, depthM, intrinsics: { fx, fy, cx, cy } }
}
