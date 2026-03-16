import Fastify from 'fastify';
import cors from '@fastify/cors';
import jwt from '@fastify/jwt';
import rateLimit from '@fastify/rate-limit';
import swagger from '@fastify/swagger';
import swaggerUI from '@fastify/swagger-ui';
import { config } from './config/env';
import prisma from './config/database';

// Import routes
import { authRoutes } from './modules/auth/auth.routes';
import { roleRoutes } from './modules/auth/role.routes';
import { contactRoutes } from './modules/crm/contact.routes';
import { dealRoutes } from './modules/crm/deal.routes';
import { projectRoutes } from './modules/development/project.routes';
import { invoiceRoutes } from './modules/finance/invoice.routes';
import { employeeRoutes } from './modules/hrm/employee.routes';
import { activityRoutes } from './modules/common/activity.routes';
import { aiRoutes } from './modules/ai/chat.routes';
import { userRoutes } from './modules/admin/user.routes';
import { campaignRoutes } from './modules/crm/campaign.routes';
import { ticketRoutes } from './modules/crm/ticket.routes';
import { recruitmentRoutes } from './modules/hrm/recruitment.routes';
import { performanceRoutes } from './modules/hrm/performance.routes';
import { payrollRoutes } from './modules/hrm/payroll.routes';
import { ledgerRoutes } from './modules/finance/ledger.routes';
import { billRoutes } from './modules/finance/bill.routes';
import { pipelineRoutes } from './modules/development/pipeline.routes';
import { deploymentRoutes } from './modules/development/deployment.routes';
import { stakeholderRoutes } from './modules/stakeholder/stakeholder.routes';
import { subscriptionRoutes } from './modules/finance/subscription.routes';
import { workflowRoutes } from './modules/workflow/workflow.routes';

// Create Fastify instance
const fastify = Fastify({
  logger: {
    level: config.nodeEnv === 'development' ? 'debug' : 'info',
  },
});

// Register plugins
fastify.register(cors, {
  origin: config.cors.origin.split(",").map(o => o.trim()), // Allow all origins in development
  credentials: true,
});

fastify.register(jwt, {
  secret: config.jwt.secret,
  sign: {
    expiresIn: config.jwt.expiresIn || '24h',
  },
});

// Register rate limiting
fastify.register(rateLimit, {
  max: 100, // max requests per timeWindow
  timeWindow: '1 minute',
  errorResponseBuilder: () => {
    return {
      error: 'Too many requests',
      message: 'Rate limit exceeded. Please try again later.',
    };
  },
});

// Register Swagger
fastify.register(swagger, {
  openapi: {
    info: {
      title: 'AV-ERP API',
      description: 'Enterprise Resource Planning API for Artifact Virtual',
      version: '1.0.0',
    },
    servers: [
      {
        url: `http://localhost:${config.port}`,
        description: 'Development server',
      },
    ],
    components: {
      securitySchemes: {
        bearerAuth: {
          type: 'http',
          scheme: 'bearer',
          bearerFormat: 'JWT',
        },
      },
    },
  },
});

fastify.register(swaggerUI, {
  routePrefix: '/api/docs',
  uiConfig: {
    docExpansion: 'list',
    deepLinking: false,
  },
});

// Health check endpoint — available at both /health and /api/health
fastify.get('/health', async () => {
  return { status: 'ok', timestamp: new Date().toISOString() };
});
fastify.get('/api/health', async () => {
  return { status: 'ok', timestamp: new Date().toISOString() };
});

// Register routes
fastify.register(async (instance) => {
  instance.register(authRoutes, { prefix: '/api/auth' });
  instance.register(roleRoutes, { prefix: '/api/auth' });
  instance.register(contactRoutes, { prefix: '/api/crm' });
  instance.register(dealRoutes, { prefix: '/api/crm' });
  instance.register(projectRoutes, { prefix: '/api/development' });
  instance.register(invoiceRoutes, { prefix: '/api/finance' });
  instance.register(employeeRoutes, { prefix: '/api/hrm' });
  instance.register(activityRoutes, { prefix: '/api' });
  instance.register(aiRoutes, { prefix: '/api/ai' });
  instance.register(userRoutes, { prefix: '/api/admin' });
  instance.register(campaignRoutes, { prefix: '/api/crm' });
  instance.register(ticketRoutes, { prefix: '/api/crm' });
  instance.register(recruitmentRoutes, { prefix: '/api/hrm' });
  instance.register(performanceRoutes, { prefix: '/api/hrm' });
  instance.register(payrollRoutes, { prefix: '/api/hrm' });
  instance.register(ledgerRoutes, { prefix: '/api/finance' });
  instance.register(billRoutes, { prefix: '/api/finance' });
  instance.register(pipelineRoutes, { prefix: '/api/development' });
  instance.register(deploymentRoutes, { prefix: '/api/development' });
  instance.register(stakeholderRoutes, { prefix: '/api' });
  instance.register(workflowRoutes, { prefix: '/api' });
  instance.register(subscriptionRoutes, { prefix: '/api' });
});

// Start server
const start = async () => {
  try {
    // Test database connection
    await prisma.$connect();
    fastify.log.info('Database connected successfully');

    await fastify.listen({ port: config.port, host: '0.0.0.0' });
    fastify.log.info(`Server listening on port ${config.port}`);
    fastify.log.info(`Swagger documentation available at http://localhost:${config.port}/api/docs`);
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

// Graceful shutdown
process.on('SIGINT', async () => {
  await prisma.$disconnect();
  await fastify.close();
  process.exit(0);
});

start();
