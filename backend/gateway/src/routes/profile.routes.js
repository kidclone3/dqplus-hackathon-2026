const { Router } = require('express');
const profileService = require('../services/profile.service');
const authenticate = require('../middleware/authenticate');

const router = Router();

router.use(authenticate);

/**
 * @openapi
 * /profiles:
 *   post:
 *     summary: Create a profile and link it to the current user
 *     tags: [Profiles]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             allOf:
 *               - $ref: '#/components/schemas/ProfileInput'
 *               - type: object
 *                 required: [company_name]
 *     responses:
 *       201:
 *         description: Profile created and linked to the current user
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/Profile'
 *       400:
 *         description: Missing or invalid fields
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/Error'
 *       404:
 *         description: User not found
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/Error'
 *       409:
 *         description: User already has a profile
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/Error'
 */
router.post('/', async (req, res, next) => {
  try {
    const { company_name: companyName } = req.body;
    if (!companyName) {
      return res.status(400).json({ error: 'company_name is required' });
    }

    const profile = await profileService.createProfile(req.user.sub, req.body);
    res.status(201).json(profile);
  } catch (err) {
    next(err);
  }
});

/**
 * @openapi
 * /profiles/{id}:
 *   get:
 *     summary: Get a profile by id
 *     tags: [Profiles]
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *           format: uuid
 *     responses:
 *       200:
 *         description: Profile found
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/Profile'
 *       404:
 *         description: Profile not found
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/Error'
 */
router.get('/:id', async (req, res, next) => {
  try {
    const profile = await profileService.getProfile(req.params.id);
    res.json(profile);
  } catch (err) {
    next(err);
  }
});

/**
 * @openapi
 * /profiles/{id}:
 *   patch:
 *     summary: Update the current user's profile
 *     tags: [Profiles]
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *           format: uuid
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             $ref: '#/components/schemas/ProfileInput'
 *     responses:
 *       200:
 *         description: Profile updated
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/Profile'
 *       403:
 *         description: Profile does not belong to the current user
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/Error'
 *       404:
 *         description: Profile not found
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/Error'
 */
router.patch('/:id', async (req, res, next) => {
  try {
    const profile = await profileService.updateProfile(req.user.sub, req.params.id, req.body);
    res.json(profile);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
