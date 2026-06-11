export type AccessMode = 'localhost' | 'lan' | 'tunnel'

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]'])

/** 判断当前页面是否通过 localhost 访问（与后端同机开发） */
export function getAccessMode(): AccessMode {
  const host = window.location.hostname.toLowerCase()

  if (LOCAL_HOSTS.has(host)) {
    return 'localhost'
  }

  if (host.includes('cpolar') || host.includes('ngrok') || host.includes('frp.')) {
    return 'tunnel'
  }

  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) {
    return 'lan'
  }

  // 其他公网域名，保守视为远程/穿透访问
  return 'tunnel'
}

/** 是否可在后端本机弹出 Playwright 浏览器（仅 localhost 可靠） */
export function canUseServerBrowser(): boolean {
  return getAccessMode() === 'localhost'
}

export function accessModeLabel(mode: AccessMode): string {
  switch (mode) {
    case 'localhost':
      return '本机访问'
    case 'lan':
      return '局域网访问'
    case 'tunnel':
      return '远程/穿透访问'
  }
}

export function accessModeHint(mode: AccessMode): string {
  switch (mode) {
    case 'localhost':
      return '可在本机弹出浏览器登录并保存；也可在当前设备打开登录页。'
    case 'lan':
      return '您正通过局域网访问。登录后请复制 Cookie 并点击「保存远程登录态」。'
    case 'tunnel':
      return '您正通过内网穿透/远程访问。登录后请复制 Cookie 并点击「保存远程登录态」。'
  }
}
