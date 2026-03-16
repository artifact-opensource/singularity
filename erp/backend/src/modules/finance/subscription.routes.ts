/**
 * Creem Subscription & Billing Routes
 * 
 * Webhook handler for Creem payment events + checkout/tier endpoints.
 * HMAC-SHA256 signature verification on all webhook calls.
 */
import { FastifyInstance, FastifyRequest, FastifyReply } from 'fastify';
import { createHmac } from 'crypto';
import prisma from '../../config/database';

// ── Product → Tier Mapping (test mode IDs) ──────────────────────────
const PRODUCT_TIER_MAP: Record<string, string> = {
  'prod_1QTNd25soJcgp6TxJmTCuw': 'business',    // ERP Business $49.99/mo
  'prod_b3sm0reFd97X3VQOx0YqW': 'enterprise',   // ERP Enterprise $199.99/mo
};

// ── Tier Definitions ────────────────────────────────────────────────
const TIERS = [
  { id: 'starter', name: 'Starter', price: 0, currency: 'USD', interval: 'month', features: ['5 users', 'Basic modules', 'Community support'] },
  { id: 'business', name: 'Business', price: 4999, currency: 'USD', interval: 'month', features: ['25 users', 'All modules', 'Priority support', 'API access'], creemProductId: 'prod_1QTNd25soJcgp6TxJmTCuw' },
  { id: 'enterprise', name: 'Enterprise', price: 19999, currency: 'USD', interval: 'month', features: ['Unlimited users', 'All modules', 'Dedicated support', 'Custom integrations', 'SLA'], creemProductId: 'prod_b3sm0reFd97X3VQOx0YqW' },
];

// ── Signature Verification ──────────────────────────────────────────
function verifyCreemSignature(payload: string, signature: string, secret: string): boolean {
  const expected = createHmac('sha256', secret).update(payload).digest('hex');
  return expected === signature;
}

// ── Audit Logger ────────────────────────────────────────────────────
function auditBilling(action: string, details: Record<string, unknown>) {
  const entry = { ts: new Date().toISOString(), action, ...details };
  console.log(`[billing-audit] ${JSON.stringify(entry)}`);
}

// ── Route Registration ──────────────────────────────────────────────
export async function subscriptionRoutes(fastify: FastifyInstance) {

  // ── GET /billing/tiers — Public tier listing ────────────────────
  fastify.get('/billing/tiers', async (_req: FastifyRequest, reply: FastifyReply) => {
    return reply.send({
      tiers: TIERS.map(t => ({
        id: t.id,
        name: t.name,
        price: t.price,
        currency: t.currency,
        interval: t.interval,
        features: t.features,
      })),
    });
  });

  // ── POST /billing/checkout — Create Creem checkout session ──────
  fastify.post('/billing/checkout', async (req: FastifyRequest, reply: FastifyReply) => {
    const { tierId, customerEmail, customerName } = req.body as {
      tierId: string;
      customerEmail: string;
      customerName?: string;
    };

    if (!tierId || !customerEmail) {
      return reply.status(400).send({ error: 'tierId and customerEmail required' });
    }

    const tier = TIERS.find(t => t.id === tierId);
    if (!tier || !tier.creemProductId) {
      return reply.status(400).send({ error: `Invalid tier: ${tierId}` });
    }

    const apiKey = process.env.CREEM_API_KEY;
    if (!apiKey) {
      return reply.status(500).send({ error: 'Payment gateway not configured' });
    }

    const isTest = apiKey.startsWith('creem_test_');
    const baseUrl = isTest ? 'https://test-api.creem.io' : 'https://api.creem.io';

    try {
      const response = await fetch(`${baseUrl}/v1/checkouts`, {
        method: 'POST',
        headers: {
          'x-api-key': apiKey,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          product_id: tier.creemProductId,
          success_url: `${process.env.ERP_BASE_URL || 'https://erp.artifactvirtual.com'}/billing/success`,
          metadata: {
            referenceId: `erp_${customerEmail}`,
            customerEmail,
            customerName: customerName || '',
            tier: tier.id,
          },
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        auditBilling('checkout_failed', { tier: tierId, email: customerEmail, error: data });
        return reply.status(502).send({ error: 'Payment gateway error', details: data });
      }

      auditBilling('checkout_created', { tier: tierId, email: customerEmail, checkoutId: data.id });
      return reply.send({ checkoutUrl: data.checkout_url, checkoutId: data.id });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      auditBilling('checkout_error', { tier: tierId, email: customerEmail, error: message });
      return reply.status(500).send({ error: 'Failed to create checkout session' });
    }
  });

  // ── POST /webhooks/creem — Creem webhook handler ────────────────
  fastify.post('/webhooks/creem', {
    config: { rawBody: true },
  }, async (req: FastifyRequest, reply: FastifyReply) => {
    const secret = process.env.CREEM_WEBHOOK_SECRET;
    if (!secret) {
      console.error('[creem-webhook] CREEM_WEBHOOK_SECRET not configured');
      return reply.status(500).send({ error: 'Webhook not configured' });
    }

    // Verify signature
    const signature = (req.headers['creem-signature'] as string) || '';
    const rawBody = typeof req.body === 'string' ? req.body : JSON.stringify(req.body);

    if (!verifyCreemSignature(rawBody, signature, secret)) {
      console.error('[creem-webhook] Invalid signature');
      auditBilling('webhook_signature_invalid', { signature });
      return reply.status(401).send({ error: 'Invalid signature' });
    }

    const event = req.body as {
      eventType: string;
      object: {
        id: string;
        product_id: string;
        customer: { id: string; email: string; name?: string };
        status: string;
        current_period_start?: string;
        current_period_end?: string;
        metadata?: { referenceId?: string; customerEmail?: string; tier?: string };
      };
    };

    const { eventType, object: obj } = event;
    const email = obj.metadata?.customerEmail || obj.customer?.email || '';
    const tier = obj.metadata?.tier || PRODUCT_TIER_MAP[obj.product_id] || 'starter';

    console.log(`[creem-webhook] ${eventType} — email=${email} tier=${tier} sub=${obj.id}`);

    try {
      switch (eventType) {
        case 'checkout.completed':
        case 'subscription.active':
        case 'subscription.paid': {
          await prisma.subscription.upsert({
            where: { creemSubscriptionId: obj.id },
            update: {
              status: 'active',
              tier,
              creemCustomerId: obj.customer?.id,
              creemProductId: obj.product_id,
              currentPeriodStart: obj.current_period_start ? new Date(obj.current_period_start) : undefined,
              currentPeriodEnd: obj.current_period_end ? new Date(obj.current_period_end) : undefined,
              updatedAt: new Date(),
            },
            create: {
              creemSubscriptionId: obj.id,
              creemCustomerId: obj.customer?.id,
              creemProductId: obj.product_id,
              customerEmail: email,
              customerName: obj.customer?.name,
              tier,
              status: 'active',
              currentPeriodStart: obj.current_period_start ? new Date(obj.current_period_start) : undefined,
              currentPeriodEnd: obj.current_period_end ? new Date(obj.current_period_end) : undefined,
            },
          });
          auditBilling('subscription_activated', { email, tier, subscriptionId: obj.id });
          break;
        }

        case 'subscription.canceled':
        case 'subscription.expired': {
          await prisma.subscription.updateMany({
            where: { creemSubscriptionId: obj.id },
            data: { status: eventType.split('.')[1], canceledAt: new Date(), updatedAt: new Date() },
          });
          auditBilling('subscription_ended', { email, tier, reason: eventType, subscriptionId: obj.id });
          break;
        }

        case 'subscription.past_due': {
          await prisma.subscription.updateMany({
            where: { creemSubscriptionId: obj.id },
            data: { status: 'past_due', updatedAt: new Date() },
          });
          auditBilling('subscription_past_due', { email, tier, subscriptionId: obj.id });
          break;
        }

        case 'subscription.paused': {
          await prisma.subscription.updateMany({
            where: { creemSubscriptionId: obj.id },
            data: { status: 'paused', updatedAt: new Date() },
          });
          auditBilling('subscription_paused', { email, tier, subscriptionId: obj.id });
          break;
        }

        default:
          console.log(`[creem-webhook] Unhandled event: ${eventType}`);
          auditBilling('webhook_unhandled', { eventType, subscriptionId: obj.id });
      }

      return reply.status(200).send({ received: true });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      console.error(`[creem-webhook] Error processing ${eventType}:`, message);
      auditBilling('webhook_error', { eventType, error: message, subscriptionId: obj.id });
      return reply.status(500).send({ error: 'Webhook processing failed' });
    }
  });

  // ── GET /billing/subscription — Get subscription by email ───────
  fastify.get('/billing/subscription', async (req: FastifyRequest, reply: FastifyReply) => {
    const { email } = req.query as { email: string };
    if (!email) {
      return reply.status(400).send({ error: 'email query param required' });
    }

    const sub = await prisma.subscription.findFirst({
      where: { customerEmail: email },
      orderBy: { updatedAt: 'desc' },
    });

    if (!sub) {
      return reply.send({ tier: 'starter', status: 'active', features: TIERS[0].features });
    }

    const tierDef = TIERS.find(t => t.id === sub.tier) || TIERS[0];
    return reply.send({
      tier: sub.tier,
      status: sub.status,
      features: tierDef.features,
      currentPeriodEnd: sub.currentPeriodEnd,
      subscriptionId: sub.creemSubscriptionId,
    });
  });
}
