const app = require('./app');
const { sequelize } = require('./models');

const port = process.env.PORT || 3000;
const host = process.env.HOST || '0.0.0.0';

async function start() {
  await sequelize.authenticate();
  if (process.env.NODE_ENV !== 'production') {
    await sequelize.sync();
  }

  app.listen(port, host, () => {
    console.log(`Gateway listening on ${host}:${port}`);
  });
}

start().catch((err) => {
  console.error('Failed to start gateway:', err);
  process.exit(1);
});
