const jwt = require('jsonwebtoken');
const { User } = require('../models');

const JWT_EXPIRES_IN = process.env.JWT_EXPIRES_IN || '1d';

function sanitize(user) {
  const plain = user.toJSON();
  delete plain.password;
  return plain;
}

function issueToken(user) {
  return jwt.sign({ sub: user.id, username: user.username, role: user.role }, process.env.JWT_SECRET, {
    expiresIn: JWT_EXPIRES_IN,
  });
}

async function register({ username, password, dob, role, profileId }) {
  const existing = await User.findOne({ where: { username } });
  if (existing) {
    const err = new Error('Username already taken');
    err.status = 409;
    throw err;
  }

  const user = await User.create({ username, password, dob, role, profileId });
  return { user: sanitize(user), token: issueToken(user) };
}

async function login({ username, password }) {
  const user = await User.scope('withPassword').findOne({ where: { username } });
  if (!user || !(await user.verifyPassword(password))) {
    const err = new Error('Invalid credentials');
    err.status = 401;
    throw err;
  }

  return { user: sanitize(user), token: issueToken(user) };
}

module.exports = { register, login };
