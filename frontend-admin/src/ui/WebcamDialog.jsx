// [교체 가능] PC 웹캠 촬영.
//
// 모바일은 <input capture>로 OS 카메라를 부르면 되지만 데스크톱 브라우저는 그 속성을
// 무시한다. PC에서도 찍으려면 getUserMedia로 직접 미리보기를 띄우고 canvas로 한 장
// 뽑는 수밖에 없다.
//
// 뽑은 결과는 File이다. 뒤쪽 파이프라인(EXIF 읽기 -> 축소 -> 업로드)이 File을 받게
// 되어 있고, 여기서 그 계약을 바꾸지 않는다. 웹캠 캡처에는 EXIF가 없으므로 초점거리는
// 기본값으로 추정된다 — 정확도가 떨어지는 경로라 화면에도 그렇게 적는다.
import { useEffect, useRef, useState } from "react";

export default function WebcamDialog({ onCapture, onCancel }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [error, setError] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let alive = true;
    navigator.mediaDevices
      // 화물칸을 찍는 용도라 후면 카메라를 선호한다. 노트북은 전면뿐이라 무시된다.
      ?.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 } } })
      .then((stream) => {
        if (!alive) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
        setReady(true);
      })
      .catch((err) => {
        if (!alive) return;
        setError(
          err?.name === "NotAllowedError"
            ? "카메라 권한이 거부됐습니다. 브라우저 주소창의 카메라 아이콘에서 허용해 주세요."
            : "카메라를 열지 못했습니다. 다른 프로그램이 쓰고 있는지 확인해 주세요."
        );
      });

    return () => {
      alive = false;
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const shoot = () => {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        onCapture(new File([blob], `webcam-${Date.now()}.jpg`, { type: "image/jpeg" }));
      },
      "image/jpeg",
      0.92
    );
  };

  return (
    <div className="overlay" role="dialog" aria-modal="true">
      <div className="dialog">
        <p className="dialog-title">카메라로 촬영</p>

        {error ? (
          <p className="dialog-error">{error}</p>
        ) : (
          <>
            <video ref={videoRef} className="webcam-view" autoPlay playsInline muted />
            <p className="hint">
              적재함 안쪽이 화면을 가득 채우도록, 뒷문 바로 앞에서 안쪽을 향해 찍어 주세요.
              주변 건물이나 다른 차가 함께 찍히면 그쪽 크기에 맞춰 계산됩니다.
            </p>
          </>
        )}

        <button type="button" className="btn primary" onClick={shoot} disabled={!ready}>
          촬영
        </button>
        <button type="button" className="btn secondary" onClick={onCancel}>
          취소
        </button>
      </div>
    </div>
  );
}
