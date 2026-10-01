import { relay } from '../../../lib/relay';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

type Context = { params: Promise<{ path: string[] }> };
async function handle(request: Request, context: Context) {
  return relay(request, (await context.params).path.join('/'));
}
export const GET = handle;
export const POST = handle;

export const PATCH = handle;
export const PUT = handle;
export const DELETE = handle;
