/*
 * Copyright (c) 2014-2026 Bjoern Kimminich & the OWASP Juice Shop contributors.
 * SPDX-License-Identifier: MIT
 */

import sinon from 'sinon'
import chai from 'chai'
import sinonChai from 'sinon-chai'
import * as models from '../../models/index'
import * as security from '../../lib/insecurity'
import { login } from '../../routes/login'

const expect = chai.expect
chai.use(sinonChai)

describe('login SQL injection', () => {
  const attack = "' OR 1=1--"
  let req: any
  let res: any
  let next: any
  let query: sinon.SinonStub

  beforeEach(() => {
    req = { body: { email: attack, password: 'irrelevant' } }
    res = { status: sinon.stub().returnsThis(), send: sinon.spy(), json: sinon.spy(), __: (s: string) => s }
    next = sinon.spy()
    query = sinon.stub(models.sequelize, 'query').resolves(null)
  })

  afterEach(() => {
    query.restore()
  })

  it('should not put the email into the SQL text', async () => {
    login()(req, res, next)
    await query.firstCall.returnValue

    const sql = query.firstCall.args[0] as string
    expect(sql).to.not.contain(attack)
    expect(sql).to.not.contain('OR 1=1')
  })

  it('should pass email and hashed password as replacements', async () => {
    login()(req, res, next)
    await query.firstCall.returnValue

    const options: any = query.firstCall.args[1]
    expect(options.replacements).to.deep.equal({ email: attack, password: security.hash('irrelevant') })
  })

  it('should not put the password into the SQL text', async () => {
    req.body = { email: 'jim@juice-sh.op', password: "' OR '1'='1" }
    login()(req, res, next)
    await query.firstCall.returnValue

    expect(query.firstCall.args[0] as string).to.not.contain("' OR '1'='1")
  })
})
