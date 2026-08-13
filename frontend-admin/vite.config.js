import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // MoveAI2의 nginx가 /admin/ 아래로 프록시한다. base를 안 맞추면 번들이 /assets/를
  // 찾아 기사 화면(Vue) 쪽으로 요청이 가고 흰 화면이 된다.
  base: "/admin/",
  server: {
    host: true,
    port: 5173,
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
