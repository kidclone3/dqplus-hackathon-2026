const express = require('express');
const matchRouter = require('./routes/match.routes');
const errorHandler = require('./middleware/errorHandler');
const pool = require('./config/db');

const app = express();

app.use(express.json());

app.get('/health', async (req, res) => {
  try {
    await pool.query('SELECT 1');
    res.json({ status: 'ok', db: 'connected' });
  } catch (err) {
    res.status(503).json({ status: 'degraded', db: 'unavailable' });
  }
});

app.use('/', matchRouter);

app.use((req, res) => {
  res.status(404).json({ error: 'Not found' });
});

app.use(errorHandler);

module.exports = app;
