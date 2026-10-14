import { useSearchParams } from 'react-router'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ByRoleTab } from '@/features/insights/ByRoleTab'
import { OverviewTab } from '@/features/insights/OverviewTab'
import { UnusualTab } from '@/features/insights/UnusualTab'
import { formatDate } from '@/lib/format'
import { useMeta } from '@/lib/meta'

const TABS = ['overview', 'role', 'unusual'] as const
type Tab = (typeof TABS)[number]

export default function InsightsPage() {
  const [search, setSearch] = useSearchParams()
  const meta = useMeta()
  const requested = search.get('tab') as Tab | null
  const tab: Tab = requested && TABS.includes(requested) ? requested : 'overview'
  const ratesDate = meta.data?.fx.rates_date

  return (
    <>
      <p className="mb-4 text-muted">
        Amounts across countries are in US dollars
        {ratesDate && `, using European Central Bank rates of ${formatDate(ratesDate)} (updated daily)`}. Part-time
        salaries are compared at their full-time rate.
      </p>
      <Tabs value={tab} onValueChange={(value) => setSearch({ tab: value }, { replace: true })}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="role">By role</TabsTrigger>
          <TabsTrigger value="unusual">Unusual salaries</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <OverviewTab />
        </TabsContent>
        <TabsContent value="role">
          <ByRoleTab />
        </TabsContent>
        <TabsContent value="unusual">
          <UnusualTab />
        </TabsContent>
      </Tabs>
    </>
  )
}
