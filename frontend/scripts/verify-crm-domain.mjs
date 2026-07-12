import { readFile } from 'node:fs/promises'

const [apiSource, typesSource, pageSource] = await Promise.all([
  readFile(new URL('../src/api/crm.ts', import.meta.url), 'utf8'),
  readFile(new URL('../src/types/crm.ts', import.meta.url), 'utf8'),
  readFile(new URL('../src/pages/EnterpriseWorkbenchPage.tsx', import.meta.url), 'utf8'),
])

for (const endpoint of ['/crm/leads', '/employee/daily-reports', '/daily-reports/summary']) {
  if (!apiSource.includes(endpoint)) throw new Error(`missing CRM endpoint mapping: ${endpoint}`)
}

for (const symbol of ['LeadResponse', 'FollowUpCreate', 'DailyReportCreate']) {
  if (!typesSource.includes(`interface ${symbol}`)) throw new Error(`missing CRM type: ${symbol}`)
}

for (const feature of ['useQuery', 'useMutation', 'WriteConfirmDialog']) {
  if (!pageSource.includes(feature)) throw new Error(`enterprise workbench missing: ${feature}`)
}

console.log('CRM domain frontend verified')
