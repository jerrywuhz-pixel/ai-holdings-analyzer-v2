import Link from 'next/link';
import { requireUser } from '@/lib/supabase';

export const dynamic = 'force-dynamic';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
interface PositionSnapshot {
  total_cost: number | null;
  total_quantity: number;
  market: string;
  symbol: string;
  snapshot_date: string;
}

interface TradeEvent {
  id: string;
  symbol: string;
  stock_name: string | null;
  side: 'BUY' | 'SELL';
  price: number;
  quantity: number;
  trade_amount: number | null;
  trade_date: string;
  source: string;
  market: string;
}

interface JobRow {
  status: string;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */
function formatCurrency(value: number | null | undefined, market?: string): string {
  if (value == null) return '-';
  const prefix = market === 'US' ? '$' : '¥';
  const sign = value < 0 ? '-' : '';
  return `${sign}${prefix}${Math.abs(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/* ------------------------------------------------------------------ */
/*  Page                                                                */
/* ------------------------------------------------------------------ */
export default async function HomePage() {
  const { supabase } = await requireUser();

  /* ---------- parallel queries ---------- */
  const [positionsRes, tradesRes, jobsRes] = await Promise.all([
    supabase
      .from('position_snapshots')
      .select('total_cost, total_quantity, market, symbol, snapshot_date')
      .order('snapshot_date', { ascending: false }),
    supabase
      .from('trade_events')
      .select('id, symbol, stock_name, side, price, quantity, trade_amount, trade_date, source, market')
      .order('trade_date', { ascending: false })
      .limit(5),
    supabase
      .from('job_runs')
      .select('status'),
  ]);

  /* ---------- derive stats ---------- */
  const positions: PositionSnapshot[] = positionsRes.data ?? [];
  const recentTrades: TradeEvent[] = tradesRes.data ?? [];
  const jobs: JobRow[] = jobsRes.data ?? [];

  // Total portfolio value
  const totalPortfolioValue = positions.reduce((sum, p) => sum + (p.total_cost ?? 0), 0);

  // Unique position count (latest snapshot per symbol)
  const latestSymbols = new Set<string>();
  const uniquePositions = positions.filter((p) => {
    if (latestSymbols.has(p.symbol)) return false;
    latestSymbols.add(p.symbol);
    return true;
  });
  const positionCount = uniquePositions.filter((p) => p.total_quantity > 0).length;

  // Job stats
  const jobCounts = jobs.reduce<Record<string, number>>((acc, j) => {
    acc[j.status] = (acc[j.status] || 0) + 1;
    return acc;
  }, {});
  const totalJobs = jobs.length;
  const successJobs = jobCounts['SUCCESS'] ?? 0;

  // Today's P&L — placeholder until market price integration is available
  const todayPnl: number | null = null as number | null;
  const todayPnlStr = todayPnl != null ? formatCurrency(todayPnl) : '待更新';
  const todayPnlChange = todayPnl != null ? (todayPnl >= 0 ? `+${todayPnl.toLocaleString()}` : todayPnl.toLocaleString()) : '需行情数据';
  const todayPnlPositive = todayPnl != null ? todayPnl >= 0 : true;

  /* ---------- render ---------- */
  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900">欢迎回来</h1>
      <p className="mt-1 text-sm text-gray-500">
        这里是 AI 持仓投资分析系统的 Dashboard，快速查看您的投资概况。
      </p>

      {/* Stats cards */}
      <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="总持仓市值"
          value={totalPortfolioValue > 0 ? formatCurrency(totalPortfolioValue) : '¥0.00'}
          change={positionCount > 0 ? `${positionCount} 只股票` : '暂无持仓'}
          positive={positionCount > 0}
        />
        <StatCard
          title="今日盈亏"
          value={todayPnlStr}
          change={todayPnlChange}
          positive={todayPnlPositive}
        />
        <StatCard
          title="本周任务"
          value={totalJobs > 0 ? `${successJobs} / ${totalJobs}` : '0 / 0'}
          change={totalJobs > 0 ? '已完成' : '暂无任务'}
          positive={totalJobs === 0 || successJobs > 0}
        />
        <StatCard
          title="持仓数量"
          value={String(positionCount)}
          change={positionCount > 0 ? '活跃持仓' : '-'}
          positive={positionCount > 0}
        />
      </div>

      {/* Recent trades */}
      <div className="mt-8">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium text-gray-900">最近交易</h2>
          <Link href="/transactions" className="text-sm font-medium text-primary hover:text-primary-600">
            查看全部 →
          </Link>
        </div>
        <div className="mt-4 overflow-hidden rounded-lg bg-white shadow">
          {recentTrades.length === 0 ? (
            <div className="px-6 py-10 text-center text-sm text-gray-500">
              暂无交易记录
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">日期</th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">股票</th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">方向</th>
                    <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">价格</th>
                    <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">数量</th>
                    <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">金额</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 bg-white">
                  {recentTrades.map((t) => (
                    <tr key={t.id} className="hover:bg-gray-50">
                      <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-900">{t.trade_date}</td>
                      <td className="whitespace-nowrap px-6 py-4 text-sm">
                        <Link href={`/positions/${t.symbol}`} className="font-medium text-primary hover:text-primary-600">
                          {t.stock_name || t.symbol}
                        </Link>
                        <span className="ml-1 text-xs text-gray-400">{t.symbol}</span>
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-sm">
                        <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${t.side === 'BUY' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                          {t.side === 'BUY' ? '买入' : '卖出'}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-right text-sm text-gray-900">{formatCurrency(t.price, t.market)}</td>
                      <td className="whitespace-nowrap px-6 py-4 text-right text-sm text-gray-900">{t.quantity.toLocaleString()}</td>
                      <td className="whitespace-nowrap px-6 py-4 text-right text-sm text-gray-900">{t.trade_amount != null ? formatCurrency(t.trade_amount, t.market) : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Quick actions */}
      <div className="mt-8">
        <h2 className="text-lg font-medium text-gray-900">快捷入口</h2>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <QuickAction href="/positions" title="持仓组合" desc="查看和管理您的持仓" />
          <QuickAction href="/transactions" title="交易记录" desc="查看历史交易明细" />
          <QuickAction href="/weekly" title="投资周报" desc="查看本周投资分析" />
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                      */
/* ------------------------------------------------------------------ */

function StatCard({
  title,
  value,
  change,
  positive,
}: {
  title: string;
  value: string;
  change: string;
  positive: boolean;
}) {
  return (
    <div className="overflow-hidden rounded-lg bg-white shadow">
      <div className="p-5">
        <div className="flex items-center">
          <div className="flex-1">
            <p className="truncate text-sm font-medium text-gray-500">{title}</p>
            <p className="mt-1 text-2xl font-semibold text-gray-900">{value}</p>
          </div>
        </div>
      </div>
      <div className="bg-gray-50 px-5 py-3">
        <div className="text-sm">
          <span className={`font-medium ${positive ? 'text-green-600' : 'text-red-600'}`}>
            {change}
          </span>
        </div>
      </div>
    </div>
  );
}

function QuickAction({ href, title, desc }: { href: string; title: string; desc: string }) {
  return (
    <Link
      href={href}
      className="flex items-center justify-between rounded-lg border border-gray-200 bg-white p-4 shadow-sm transition-colors hover:bg-gray-50"
    >
      <div>
        <p className="font-medium text-gray-900">{title}</p>
        <p className="text-sm text-gray-500">{desc}</p>
      </div>
      <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
      </svg>
    </Link>
  );
}
