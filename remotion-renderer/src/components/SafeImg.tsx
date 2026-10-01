import React, { useEffect, useState } from "react";
import { Img, continueRender, delayRender } from "remotion";

/** Image loader with bounded failure path; broken URLs become transparent 1x1. */
export const SafeImg: React.FC<{
  src: string;
  style?: React.CSSProperties;
  placeholderColor?: string;
}> = ({ src, style, placeholderColor = "#111118" }) => {
  const [failed, setFailed] = useState(false);
  const [handle] = useState(() => delayRender(`SafeImg loading ${src}`));

  useEffect(() => {
    let settled = false;
    const settle = (ok: boolean) => {
      if (settled) return;
      settled = true;
      if (!ok) setFailed(true);
      continueRender(handle);
    };
    const img = new Image();
    img.onload = () => settle(true);
    img.onerror = () => settle(false);
    img.src = src;
    const timer = setTimeout(() => settle(false), 5000);
    return () => clearTimeout(timer);
  }, [src, handle]);

  if (failed || !src) {
    return <div style={{ backgroundColor: placeholderColor, ...style }} />;
  }
  return <Img src={src} style={style} />;
};

export default SafeImg;
