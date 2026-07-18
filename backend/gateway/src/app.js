const express = require('express');
const cors = require('cors');
const swaggerUi = require('swagger-ui-express');
const authRouter = require('./routes/auth.routes');
const profileRouter = require('./routes/profile.routes');
const errorHandler = require('./middleware/errorHandler');
const { sequelize } = require('./models');
const swaggerSpec = require('./config/swagger');

const app = express();

const corsOrigin = process.env.CORS_ORIGIN
  ? process.env.CORS_ORIGIN.split(',')
  : /^https?:\/\/(dqplus\.ddns\.net|localhost|127\.0\.0\.1)(:\d+)?$/;
app.use(cors({ origin: corsOrigin }));
app.use(express.json());

app.get('/health', async (req, res) => {
  try {
    await sequelize.authenticate();
    res.json({ status: 'ok', db: 'connected' });
  } catch (err) {
    res.status(503).json({ status: 'degraded', db: 'unavailable' });
  }
});

app.use('/docs', swaggerUi.serve, swaggerUi.setup(swaggerSpec));
app.use('/auth', authRouter);
app.use('/profiles', profileRouter);

app.use((req, res) => {
  res.status(404).json({ error: 'Not found' });
});

app.use(errorHandler);

module.exports = app;
