// 설계서 2.1의 이미지 정책과 4.3의 intrinsic 확보를 담당한다.
//
// 이 모듈을 UI 생성 도구로 다시 만들지 말 것. 특히 focal length 보정을 빠뜨리면
// depth unprojection이 리사이즈 배율만큼 통째로 어긋나고, 그 오차가 CBM까지 그대로 간다.

export const LONG_SIDE_PX = 1024;   // 2.1: 긴 변 1024px
export const JPEG_QUALITY = 0.78;   // 2.1: 품질 75-80%

const FILM_DIAGONAL_MM = Math.hypot(36, 24); // 35mm 필름 대각선

/**
 * EXIF 방향을 픽셀에 굽고 긴 변 1024px로 축소한다.
 * canvas 재인코딩으로 EXIF가 사라지므로 방향을 여기서 확정해야 한다.
 */
export async function resizeToJpeg(file, orientation = 1) {
  const bitmap = await createImageBitmap(file);
  const swap = orientation >= 5 && orientation <= 8; // 90/270도면 가로세로가 바뀐다
  const srcW = swap ? bitmap.height : bitmap.width;
  const srcH = swap ? bitmap.width : bitmap.height;

  const ratio = Math.min(1, LONG_SIDE_PX / Math.max(srcW, srcH));
  const outW = Math.round(srcW * ratio);
  const outH = Math.round(srcH * ratio);

  const canvas = document.createElement("canvas");
  canvas.width = outW;
  canvas.height = outH;
  const ctx = canvas.getContext("2d");

  ctx.translate(outW / 2, outH / 2);
  switch (orientation) {
    case 2: ctx.scale(-1, 1); break;
    case 3: ctx.rotate(Math.PI); break;
    case 4: ctx.scale(1, -1); break;
    case 6: ctx.rotate(Math.PI / 2); break;
    case 8: ctx.rotate(-Math.PI / 2); break;
    default: break;
  }
  const drawW = swap ? outH : outW;
  const drawH = swap ? outW : outH;
  ctx.drawImage(bitmap, -drawW / 2, -drawH / 2, drawW, drawH);
  bitmap.close();

  const blob = await new Promise((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY)
  );
  return { blob, width: outW, height: outH, srcW, srcH, ratio };
}

/**
 * 4.3 우선순위 1(EXIF)로 camera intrinsic을 만든다.
 * 2.1: "리사이즈 비율만큼 focal length in pixels도 동일하게 보정한다."
 * EXIF에 focal 정보가 없으면 null을 돌려주고, 서버가 4.3 우선순위 4(기본 화각)로 떨어진다.
 */
export function buildIntrinsics(exif, resized) {
  const { width, height, srcW, srcH } = resized;

  let focalPxOriginal = null;
  if (exif.focal35) {
    // 35mm 환산 초점거리 -> 원본 픽셀 초점거리
    const diagPx = Math.hypot(srcW, srcH);
    focalPxOriginal = exif.focal35 * (diagPx / FILM_DIAGONAL_MM);
  }
  if (focalPxOriginal === null) return null;

  // 원본 기준 focal을 리사이즈 배율로 축소한다. 이 한 줄이 빠지면 전체가 틀어진다.
  const scale = width / srcW;
  const f = focalPxOriginal * scale;

  return { fx: f, fy: f, cx: width / 2, cy: height / 2 };
}
