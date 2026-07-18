const sequelize = require('../config/database');
const User = require('./user.model');
const Profile = require('./profile.model');

Profile.hasMany(User, { foreignKey: 'profileId', as: 'users' });
User.belongsTo(Profile, { foreignKey: 'profileId', as: 'profile' });

module.exports = { sequelize, User, Profile };
