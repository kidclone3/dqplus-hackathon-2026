const app = require('./app');

const port = process.env.PORT || 3002;

app.listen(port, () => {
  console.log(`Matching engine listening on port ${port}`);
});
