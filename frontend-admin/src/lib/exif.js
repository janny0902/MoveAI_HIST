// 설계서 2.1: "원본에서 EXIF 방향, focal length 및 35mm equivalent focal length를 먼저 읽는다."
//
// 이 모듈을 UI 생성 도구(Stitch / AI Studio)로 다시 만들지 말 것.
// 리사이즈하면 EXIF가 사라지므로 반드시 축소 전 원본 바이트에서 읽어야 하고,
// 여기서 얻은 focal length가 뒤의 intrinsic 보정과 depth unprojection 정확도를 결정한다.

const TAG_ORIENTATION = 0x0112;
const TAG_FOCAL_LENGTH = 0x920a;
const TAG_FOCAL_35MM = 0xa405;
const TAG_EXIF_IFD_POINTER = 0x8769;
const TYPE_RATIONAL = 5;

/**
 * JPEG 바이트에서 필요한 EXIF 태그만 뽑는다.
 * @returns {{orientation?: number, focalMm?: number, focal35?: number}}
 */
export function parseExif(buffer) {
  const view = new DataView(buffer);
  if (view.byteLength < 4 || view.getUint16(0) !== 0xffd8) return {};

  let offset = 2;
  while (offset + 4 < view.byteLength) {
    const marker = view.getUint16(offset);
    if (marker === 0xffe1) {
      const tiffBase = offset + 10; // APP1 마커(2) + 길이(2) + "Exif\0\0"(6)
      if (tiffBase + 8 > view.byteLength) return {};
      const little = view.getUint16(tiffBase) === 0x4949;
      const ifd0 = tiffBase + view.getUint32(tiffBase + 4, little);
      return readIfds(view, tiffBase, ifd0, little);
    }
    // APP1이 아니면 세그먼트 길이만큼 건너뛴다.
    const size = view.getUint16(offset + 2);
    if (size <= 0) break;
    offset += 2 + size;
  }
  return {};
}

function readIfds(view, tiffBase, ifd0Offset, little) {
  const out = {};
  readIfd(view, tiffBase, ifd0Offset, little, out);
  // focal length 태그는 대개 IFD0이 아니라 Exif SubIFD에 있다.
  if (out.exifIfd) readIfd(view, tiffBase, out.exifIfd, little, out);
  delete out.exifIfd;
  return out;
}

function readIfd(view, tiffBase, start, little, into) {
  if (start + 2 > view.byteLength) return;
  const count = view.getUint16(start, little);
  for (let i = 0; i < count; i++) {
    const entry = start + 2 + i * 12;
    if (entry + 12 > view.byteLength) return;
    const tag = view.getUint16(entry, little);
    const type = view.getUint16(entry + 2, little);
    const valueOffset = entry + 8;

    if (tag === TAG_ORIENTATION) {
      into.orientation = view.getUint16(valueOffset, little);
    } else if (tag === TAG_FOCAL_35MM) {
      into.focal35 = view.getUint16(valueOffset, little);
    } else if (tag === TAG_EXIF_IFD_POINTER) {
      into.exifIfd = tiffBase + view.getUint32(valueOffset, little);
    } else if (tag === TAG_FOCAL_LENGTH && type === TYPE_RATIONAL) {
      // RATIONAL은 값이 아니라 분자/분모가 있는 위치를 담는다.
      const p = tiffBase + view.getUint32(valueOffset, little);
      if (p + 8 <= view.byteLength) {
        const num = view.getUint32(p, little);
        const den = view.getUint32(p + 4, little);
        if (den) into.focalMm = num / den;
      }
    }
  }
}
