/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 분리 배포 시 API 서버 origin (예: https://ripple-api.onrender.com). 비우면 같은 서버의 /api */
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
