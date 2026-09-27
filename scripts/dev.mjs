import { spawn } from 'node:child_process'
import net from 'node:net'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dir = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(__dir, '..')

// 探测一个空闲端口，从 start 开始递增
function getFreePort(start = 8000) {
  return new Promise((resolve, reject) => {
    const srv = net.createServer()
    srv.unref?.()
    srv.on('error', (err) => {
      if (err.code === 'EADDRINUSE') {
        // 端口被占用，尝试下一个
        getFreePort(start + 1).then(resolve, reject)
      } else {
        reject(err)
      }
    })
    srv.listen({ host: '127.0.0.1', port: start }, () => {
      const port = srv.address().port
      srv.close(() => resolve(port))
    })
  })
}

function launch(cmd, args, env, cwd) {
  return spawn(cmd, args, {
    cwd: cwd || ROOT,
    env: { ...process.env, ...env },
    stdio: 'inherit',
  })
}

async function main() {
  // 后端默认 8000，前端默认 5173
  const backendPort = await getFreePort(8000)
  const frontendPort = await getFreePort(5173)

  console.log('')
  console.log('════════════════════════════════════════════════')
  console.log('  📝 在线考试与题库管理系统 - 开发服务器')
  console.log(`  后端 API : http://127.0.0.1:${backendPort}  (/docs)`)
  console.log(`  前端页面 : http://127.0.0.1:${frontendPort}`)
  console.log('════════════════════════════════════════════════')
  if (backendPort !== 8000) console.log(`  ⚠ 默认后端端口 8000 被占用，已切换到 ${backendPort}`)
  if (frontendPort !== 5173) console.log(`  ⚠ 默认前端端口 5173 被占用，已切换到 ${frontendPort}`)
  console.log('')

  const pyCmd = process.platform === 'win32' ? 'python' : 'python3'
  const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm'

  const backend = launch(
    pyCmd,
    ['-m', 'uvicorn', 'app.main:app', '--reload', '--port', String(backendPort)],
    { BACKEND_PORT: String(backendPort), FRONTEND_PORT: String(frontendPort) },
    ROOT,
  )

  const frontend = launch(
    npmCmd,
    ['run', 'dev'],
    { FRONTEND_PORT: String(frontendPort), BACKEND_PORT: String(backendPort) },
    resolve(ROOT, 'frontend'),
  )

  const cleanup = () => {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(backend.pid), '/T', '/F'])
      spawn('taskkill', ['/pid', String(frontend.pid), '/T', '/F'])
    } else {
      backend.kill('SIGTERM')
      frontend.kill('SIGTERM')
    }
    process.exit(0)
  }
  process.on('SIGINT', cleanup)
  process.on('SIGTERM', cleanup)
  process.on('exit', cleanup)

  backend.on('exit', (code) => {
    console.error(`\n后端进程退出 (code=${code})`)
    if (code !== 0) process.exit(code)
  })
  frontend.on('exit', (code) => {
    console.error(`\n前端进程退出 (code=${code})`)
    if (code !== 0) process.exit(code)
  })
}

main().catch((err) => {
  console.error('启动失败：', err)
  process.exit(1)
})