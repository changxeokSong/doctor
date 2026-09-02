const CATEGORY_PREFIX = '일상생활 수어 > '

export const stripCategory = (c: string) => (c.startsWith(CATEGORY_PREFIX) ? c.slice(CATEGORY_PREFIX.length) : c)
