const { Profile, User } = require('../models');

async function createProfile(userId, data) {
  const user = await User.findByPk(userId);
  if (!user) {
    const err = new Error('User not found');
    err.status = 404;
    throw err;
  }
  if (user.profileId) {
    const err = new Error('User already has a profile');
    err.status = 409;
    throw err;
  }

  const profile = await Profile.create(data);
  user.profileId = profile.id;
  await user.save();
  return profile;
}

async function updateProfile(userId, profileId, data) {
  const user = await User.findByPk(userId);
  if (!user || user.profileId !== profileId) {
    const err = new Error('Forbidden');
    err.status = 403;
    throw err;
  }

  const profile = await Profile.findByPk(profileId);
  if (!profile) {
    const err = new Error('Profile not found');
    err.status = 404;
    throw err;
  }

  await profile.update(data);
  return profile;
}

async function getProfile(profileId) {
  const profile = await Profile.findByPk(profileId);
  if (!profile) {
    const err = new Error('Profile not found');
    err.status = 404;
    throw err;
  }
  return profile;
}

module.exports = { createProfile, updateProfile, getProfile };
