/**
 * Vitest 测试环境初始化。
 *
 * 在每个测试文件执行前加载 jest-dom 的 DOM 断言扩展
 * （如 toBeInTheDocument、toHaveTextContent 等）。
 * 同时 mock jsdom 不支持的浏览器 API。
 */

import '@testing-library/jest-dom/vitest'

// jsdom 不支持 scrollIntoView，需要 mock
Element.prototype.scrollIntoView = () => {}
