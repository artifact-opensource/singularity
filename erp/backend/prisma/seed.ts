import { PrismaClient } from '@prisma/client';
import { PrismaPg } from '@prisma/adapter-pg';
import { Pool } from 'pg';
import bcrypt from 'bcrypt';
import 'dotenv/config';

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});

const adapter = new PrismaPg(pool);
const prisma = new PrismaClient({ adapter });

async function main() {
  console.log('🌱 Seeding auth infrastructure...\n');

  // ============================================================
  // ROLES
  // ============================================================
  const adminRole = await prisma.role.upsert({
    where: { name: 'admin' },
    update: {},
    create: {
      name: 'admin',
      description: 'Administrator with full access',
      permissions: ['*'],
    },
  });

  await prisma.role.upsert({
    where: { name: 'manager' },
    update: {},
    create: {
      name: 'manager',
      description: 'Department manager with elevated access',
      permissions: ['read:all', 'write:own', 'manage:team'],
    },
  });

  await prisma.role.upsert({
    where: { name: 'user' },
    update: {},
    create: {
      name: 'user',
      description: 'Standard user role',
      permissions: ['read:own', 'write:own'],
    },
  });

  await prisma.role.upsert({
    where: { name: 'viewer' },
    update: {},
    create: {
      name: 'viewer',
      description: 'Read-only access',
      permissions: ['read:own'],
    },
  });

  console.log('✅ Roles created (admin, manager, user, viewer)');

  // ============================================================
  // USERS
  // ============================================================
  const adminPw = process.env.SEED_ADMIN_PASSWORD;
  if (!adminPw) {
    console.error('FATAL: SEED_ADMIN_PASSWORD env var required');
    process.exit(1);
  }
  const devPw = process.env.SEED_DEV_PASSWORD;
  if (!devPw) {
    console.error('FATAL: SEED_DEV_PASSWORD env var required');
    process.exit(1);
  }

  await prisma.user.upsert({
    where: { email: 'admin@artifactvirtual.com' },
    update: { password: await bcrypt.hash(adminPw, 12) },
    create: {
      email: 'admin@artifactvirtual.com',
      password: await bcrypt.hash(adminPw, 12),
      firstName: 'Admin',
      lastName: 'User',
      roleId: adminRole.id,
      isActive: true,
    },
  });

  await prisma.user.upsert({
    where: { email: 'admin@example.com' },
    update: { password: await bcrypt.hash(devPw, 12) },
    create: {
      email: 'admin@example.com',
      password: await bcrypt.hash(devPw, 12),
      firstName: 'Ali',
      lastName: 'Shakil',
      roleId: adminRole.id,
      isActive: true,
    },
  });

  console.log('✅ Users created (admin, ali.shakil)');

  // ============================================================
  // SUMMARY
  // ============================================================
  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('  AUTH INFRASTRUCTURE SEEDED');
  console.log('═══════════════════════════════════════════════════════════');
  console.log('  Roles: 4');
  console.log('  Users: 2');
  console.log('  Business data: NONE (enter real data via the UI)');
  console.log('═══════════════════════════════════════════════════════════\n');
}

main()
  .then(async () => {
    await prisma.$disconnect();
    await pool.end();
  })
  .catch(async (e) => {
    console.error(e);
    await prisma.$disconnect();
    await pool.end();
    process.exit(1);
  });
