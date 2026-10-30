"use client";

import { ChartColumn } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { LatencyChart, TrafficChart, ZeroHitChart } from "@/components/charts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { NativeSelect } from "@/components/ui/input";
import { PageBody, PageHeader } from "@/components/ui/page";
import { formatCompact, formatDuration, formatNumber, formatPercent } from "@/lib/format";
import { useAnalytics, useCollections } from "@/lib/queries";

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card className="px-4 py-3.5">
      <p className="text-muted-foreground text-[12.5px]">{label}</p>
      <p className="tabular mt-1 text-[22px] leading-tight font-semibold tracking-tight">{value}</p>
      {hint ? <p className="text-subtle mt-1 truncate text-xs">{hint}</p> : null}
    </Card>
  );
}

export default function AnalyticsPage() {
  const { project } = useParams<{ project: string }>();
  const collections = useCollections(project);
  const [days, setDays] = useState(14);
  const [collection, setCollection] = useState("");
  const analytics = useAnalytics(project, days, collection || undefined);
  const data = analytics.data;
  const requests = data ? data.total_queries + data.total_answers : 0;

  return (
    <PageBody>
      <PageHeader
        title="Analytics"
        description="Production traffic: volume, latency, queries that found nothing, and what people ask."
        actions={
          <>
            <NativeSelect
              aria-label="Collection"
              className="w-44"
              value={collection}
              onChange={(e) => setCollection(e.target.value)}
            >
              <option value="">All collections</option>
              {collections.data?.map((c) => (
                <option key={c.id} value={c.slug}>
                  {c.name}
                </option>
              ))}
            </NativeSelect>
            <NativeSelect
              aria-label="Period"
              className="w-36"
              value={String(days)}
              onChange={(e) => setDays(Number(e.target.value))}
            >
              <option value="7">Last 7 days</option>
              <option value="14">Last 14 days</option>
              <option value="30">Last 30 days</option>
              <option value="90">Last 90 days</option>
            </NativeSelect>
          </>
        }
      />
      {analytics.error ? <ErrorNotice message={analytics.error.message} /> : null}
      {!data ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : requests === 0 ? (
        <Card>
          <EmptyState
            icon={<ChartColumn />}
            title="No traffic in this period"
            description="Queries and answers through the API, the SDK and the playground show up here."
          />
        </Card>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Stat label="Requests" value={formatCompact(requests)} hint={`${days} days`} />
            <Stat
              label="Answers"
              value={formatCompact(data.total_answers)}
              hint={`${formatPercent(data.total_answers / requests)} of requests`}
            />
            <Stat label="p50 latency" value={formatDuration(data.p50_ms)} />
            <Stat label="p95 latency" value={formatDuration(data.p95_ms)} />
            <Stat
              label="Zero-hit rate"
              value={formatPercent(data.zero_hit_rate, 1)}
              hint="no passage returned"
            />
            <Stat
              label="Cache hit rate"
              value={formatPercent(data.cache_hit_rate)}
              hint="served without retrieval"
            />
          </div>
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Requests per day</CardTitle>
                <CardDescription>Retrieval-only queries and cited answers.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <TrafficChart days={data.days} />
            </CardContent>
          </Card>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Latency</CardTitle>
                  <CardDescription>Server time per request, by day.</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <LatencyChart days={data.days} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Zero-hit rate</CardTitle>
                  <CardDescription>
                    Requests where retrieval returned nothing: content gaps or filters.
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <ZeroHitChart days={data.days} />
              </CardContent>
            </Card>
          </div>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Top queries</CardTitle>
                  <CardDescription>
                    The questions to put in your evaluation datasets first.
                  </CardDescription>
                </div>
              </CardHeader>
              <div
                role="region"
                aria-label="Top queries"
                tabIndex={0}
                className="mt-3 overflow-x-auto"
              >
                <table className="w-full text-[13px]">
                  <caption className="sr-only">Top queries</caption>
                  <thead className="text-subtle border-border border-y text-left text-xs">
                    <tr>
                      <th className="px-5 py-2 font-medium">Query</th>
                      <th className="hidden px-3 py-2 font-medium sm:table-cell">Collection</th>
                      <th className="px-5 py-2 text-right font-medium">Count</th>
                    </tr>
                  </thead>
                  <tbody className="divide-border divide-y">
                    {data.top_queries.map((row) => (
                      <tr key={`${row.collection_slug}-${row.query}`}>
                        <td className="max-w-0 px-5 py-2">
                          <Link
                            href={`/p/${project}/playground?collection=${row.collection_slug}&q=${encodeURIComponent(row.query)}`}
                            className="block truncate hover:underline"
                          >
                            {row.query}
                          </Link>
                        </td>
                        <td className="text-muted-foreground hidden px-3 py-2 sm:table-cell">
                          {row.collection}
                        </td>
                        <td className="tabular px-5 py-2 text-right">{formatNumber(row.count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>By collection</CardTitle>
                  <CardDescription>Volume and tail latency per corpus.</CardDescription>
                </div>
              </CardHeader>
              <div className="mt-3">
                <table className="w-full text-[13px]">
                  <caption className="sr-only">Requests by collection</caption>
                  <thead className="text-subtle border-border border-y text-left text-xs">
                    <tr>
                      <th className="px-5 py-2 font-medium">Collection</th>
                      <th className="px-3 py-2 text-right font-medium">Requests</th>
                      <th className="px-5 py-2 text-right font-medium">p95</th>
                    </tr>
                  </thead>
                  <tbody className="divide-border divide-y">
                    {data.by_collection.map((row) => (
                      <tr key={row.slug}>
                        <td className="px-5 py-2">
                          <Link
                            href={`/p/${project}/collections/${row.slug}`}
                            className="hover:underline"
                          >
                            {row.name}
                          </Link>
                        </td>
                        <td className="tabular px-3 py-2 text-right">
                          {formatNumber(row.queries)}
                        </td>
                        <td className="tabular px-5 py-2 text-right">
                          {formatDuration(row.p95_ms)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        </div>
      )}
    </PageBody>
  );
}
