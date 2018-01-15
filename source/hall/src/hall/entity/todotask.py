# -*- coding=utf-8
'''
Created on 2015年7月7日

@author: zhaojiangang
'''
from sre_compile import isstring

import freetime.util.log as ftlog
import poker.util.timestamp as pktimestamp
from freetime.entity.msg import MsgPack
from hall.entity import hallconf
from poker.entity.biz.confobj import TYConfable, TYConfableRegister
from poker.entity.biz.content import TYContentUtils
from poker.entity.biz.exceptions import TYBizException, TYBizConfException
from poker.entity.biz.store.store import TYProduct
from poker.entity.dao import userdata
from poker.entity.game.game import TYGame
from poker.protocol import router
from poker.util import strutil


class TodoTaskHelper(object):
    @classmethod
    def getParamsByProduct(cls, product):
        from hall.entity import hallitem
        params = {
            'id': product.productId,
            'name': product.displayName,
            'price': product.price,
            'desc': product.desc,
            'type': 1,
            'addchip': TYContentUtils.getMinFixedAssetCount(product.content, hallitem.ASSET_CHIP_KIND_ID),
            'buy_type': product.buyType,
            'picurl': product.pic,
            'tip': product.content.desc if product.content else ''
        }
        if product.priceDiamond:
            params['price_diamond'] = product.priceDiamond
        if product.diamondExchangeRate:
            params['exchange_rate'] = product.diamondExchangeRate
        return params

    @classmethod
    def makeTodoTaskMsg(cls, gameId, userId, todotasks):
        mo = MsgPack()
        mo.setCmd('todo_tasks')
        mo.setResult('gameId', gameId)
        mo.setResult('userId', userId)
        mo.setResult('tasks', cls.encodeTodoTasks(todotasks))
        return mo

    @classmethod
    def sendTodoTask(cls, gameId, userId, todotasks):
        mo = cls.makeTodoTaskMsg(gameId, userId, todotasks)
        router.sendToUser(mo, userId)
        return mo

    @classmethod
    def encodeTodoTasks(cls, todotasks):
        assert (isinstance(todotasks, (list, TodoTask)))
        if isinstance(todotasks, list):
            return [t.toDict() for t in todotasks]
        return [todotasks.toDict()]

    @classmethod
    def makeTodoTasksByFactory(cls, gameId, userId, clientId, todotaskFactoryList):
        ret = []
        for todotaskFactory in todotaskFactoryList:
            todotask = todotaskFactory.newTodoTask(gameId, userId, clientId)
            if todotask:
                ret.append(todotask)
            else:
                ftlog.debug('TodoTaskHelper.makeTodoTasksByFactory gameId=', gameId,
                            'userId=', userId,
                            'clientId=', clientId,
                            'todotaskFactory=', todotaskFactory,
                            'fields=', todotaskFactory.__dict__)
        return ret

    @classmethod
    def canGainReward(cls, states):
        for state_ in states:
            if state_['st'] == 1:
                return True
        return False

    @classmethod
    def makeTodoTaskNsloginReward(cls, gameId, userId, clientId):
        _, clientVer, _ = strutil.parseClientId(clientId)
        if clientVer >= 3.76:
            return None
        from hall.entity import halldailycheckin, hallitem, hallstore
        timestamp = pktimestamp.getCurrentTimestamp()
        states = halldailycheckin.dailyCheckin.getStates(gameId, userId, timestamp)
        if not cls.canGainReward(states):
            return None

        todotask = TodoTaskNsloginReward(cls.translateDailyCheckinStates(states))
        closeMember = hallconf.getClientDailyCheckinConf(clientId).get('closeMember')

        userAssets = hallitem.itemSystem.loadUserAssets(userId)
        remainDays = userAssets.balance(gameId, hallitem.ASSET_ITEM_MEMBER_KIND_ID, timestamp)
        isMember = remainDays > 0
        memberBonus = 30000
        todotask.setMemberInfo(isMember, remainDays, memberBonus)

        if not closeMember and not isMember:
            product, _shelves = hallstore.findProductByContains(gameId, userId, clientId,
                                                                None, None,
                                                                hallitem.ASSET_ITEM_MEMBER_KIND_ID,
                                                                1)
            if product:
                todotask.setSubCmd(TodoTaskPayOrder(product))
        return todotask

    @classmethod
    def makeTodoTaskSmileBuy(cls, gameId, userId, clientId, needChip):
        from hall.entity import hallstore, hallitem

        product, _ = hallstore.findProductByContains(gameId, userId, clientId,
                                                     ['lessbuychip'], None,
                                                     hallitem.ASSET_CHIP_KIND_ID,
                                                     needChip)
        if not product:
            return None

        return TodoTaskOrderShow.makeByProduct('金币不足，无法使用表情哦~', '', product)

    @classmethod
    def makeTodoTaskBenefitsInfo(cls, benefitsSend, userBenefits):
        if not benefitsSend:
            return None
        if userBenefits.sendChip <= 0:
            return None

        benefitsStrs = []
        benefitsStrs.append('送您%s金币翻本吧！' % (userBenefits.sendChip))
        privilegeName = userBenefits.privilege.name if userBenefits.privilege else ''
        if userBenefits.extSendChip > 0:
            benefitsStrs.append('您是%s再加赠%s金币' % (privilegeName, userBenefits.extSendChip))
        benefitsStrs.append('（%s每天%s次，今天第%s次）' % (privilegeName, userBenefits.totalMaxTimes, userBenefits.times))
        if userBenefits.privilege and userBenefits.privilege.desc:
            benefitsStrs.append('\n%s' % (userBenefits.privilege.desc))
        desc = '\n'.join(benefitsStrs)
        return TodoTaskShowInfo(desc, True)

    @classmethod
    def makeBenefitsTodoTask(cls, gameId, userId, clientId, benefitsSend, userBenefits):
        if not benefitsSend:
            return None
        benefitsStrs = []
        benefitsStrs.append('送您%s金币翻本吧！' % (userBenefits.sendChip))
        privilegeName = userBenefits.privilege.name if userBenefits.privilege else ''
        if userBenefits.extSendChip > 0:
            benefitsStrs.append('您是%s再加赠%s金币' % (privilegeName, userBenefits.extSendChip))
        benefitsStrs.append('（%s每天%s次，今天第%s次）' % (privilegeName, userBenefits.totalMaxTimes, userBenefits.times))
        if userBenefits.privilege and userBenefits.privilege.desc:
            benefitsStrs.append('\n%s' % (userBenefits.privilege.desc))
        return TodoTaskShowInfo('\n'.join(benefitsStrs), True)

    @classmethod
    def makeZhuanyunTodoTaskNew(cls, gameId, userId, clientId,
                                benefitsSend, userBenefits, roomId):
        from hall.entity import hallproductselector, hallitem
        product, _ = hallproductselector.selectZhuanyunProduct(gameId, userId, clientId, roomId)
        if not product:
            return None

        buydes = '运气不好，来个转运礼包！'
        buynote = '全国只有1%的人有机会呦！'
        payOrder = TodoTaskPayOrder(product)

        # TODO 
        #         if DizhuTodoTaskData.isZhuanyunBuyDirect(gameId, userId):
        #             return [pay_order_.toStr()]

        chip = product.getMinFixedAssetCount(hallitem.ASSET_CHIP_KIND_ID)
        buydes = strutil.replaceParams(buydes, {'priceRmb': str(product.price),
                                                'contentChip': str(chip / 10000)})
        info = TodoTaskOrderShow.makeByProduct(buydes, buynote, product)
        info.setSubCmd(payOrder)

        ftlog.debug('TodoTaskHelper.makeZhuanyunTodoTaskNew gameId=', gameId,
                    'userId=', userId,
                    'benefitsSend=', benefitsSend)
        if benefitsSend:
            cancel = cls.makeBenefitsTodoTask(gameId, userId, clientId, benefitsSend, userBenefits)
            if cancel:
                info.setSubCmdExt(cancel)
        return info

    @classmethod
    def makeZhuanyunTodoTaskByLevelName(cls, gameId, userId, clientId,
                                        benefitsSend, userBenefits, levelName):
        from hall.entity import hallproductselector, hallitem
        product, _ = hallproductselector.selectProduct(gameId, userId, clientId, levelName, "zhuanyun")
        if not product:
            return None

        buydes = '运气不好，来个转运礼包！'
        buynote = '全国只有1%的人有机会呦！'
        payOrder = TodoTaskPayOrder(product)

        chip = product.getMinFixedAssetCount(hallitem.ASSET_CHIP_KIND_ID)
        buydes = strutil.replaceParams(buydes, {'priceRmb': str(product.price),
                                                'contentChip': str(chip / 10000)})
        info = TodoTaskOrderShow.makeByProduct(buydes, buynote, product)
        info.setSubCmd(payOrder)

        ftlog.debug('TodoTaskHelper.makeZhuanyunTodoTaskByLevelName gameId=', gameId,
                    'userId=', userId,
                    'benefitsSend=', benefitsSend)
        if benefitsSend:
            cancel = cls.makeBenefitsTodoTask(gameId, userId, clientId, benefitsSend, userBenefits)
            if cancel:
                info.setSubCmdExt(cancel)
        return info

    @classmethod
    def makeWinLeadTodoTask(cls, userId, product):
        if not product: return None

        ftlog.debug('makeWinLeadTodoTask userId = ', userId, 'productId = ', product.productId)
        payorder = TodoTaskPayOrder(product)

        buydesc = '技术真高！恭喜获得超值礼包购买机会，去赢更多吧（商城买不到哦）！'

        info = TodoTaskOrderShow.makeByProduct(buydesc, '', product)
        info.setSubCmd(payorder)

        return info

    @classmethod
    def translateDailyCheckinStates(cls, states):
        rewardstate = []
        from hall.entity import hallitem
        for state in states:
            item = []
            rewardContent = state.get('rewards')
            chipCount = TYContentUtils.getMinFixedAssetCount(rewardContent, hallitem.ASSET_CHIP_KIND_ID)
            item.append('CHIP')
            item.append(chipCount)
            item.append(state.get('st'))
            rewardstate.append(item)
        return rewardstate

    @classmethod
    def makeTodoTaskPayOrder(cls, userId, clientId, product):
        payOrder = TodoTaskPayOrder(product)
        if strutil.isWinpcClient(clientId):
            payOrder.isWinpc = True
            user_diamond = userdata.getAttr(userId, 'diamond')
            if user_diamond < int(product.priceDiamond):
                payOrder.setParam('buy_type', 'charge')
                payOrder.isWinpcCharge = True
        return payOrder


class TodoTask(object):
    def __init__(self, action, params=None):
        assert (action and isstring(action))
        self._data = {'action': action, 'params': {}}
        if params:
            self.updateParams(params)

    def getAction(self):
        return self._data['action']

    def getParam(self, name, defVal):
        return self._data['params'].get(name, defVal)

    def setParam(self, name, value):
        if isinstance(value, TodoTask):
            value = value.toDict()
        self._data['params'][name] = value
        return self

    def updateParams(self, params):
        assert (isinstance(params, dict))
        for name, value in params.iteritems():
            self.setParam(name, value)
        return self

    def setSubCmd(self, subCmd):
        assert (isinstance(subCmd, TodoTask))
        self.setParam('sub_action', subCmd)
        return self

    def setCloseCmd(self, subCmd):
        assert (isinstance(subCmd, TodoTask))
        self.setParam('sub_action_close', subCmd)
        return self

    def setSubText(self, subText):
        assert (isstring(subText))
        self.setParam('sub_text', subText)
        return self

    def setSubCmdWithText(self, subCmd, text=None):
        assert (isinstance(subCmd, TodoTask))
        assert (text is None or isstring(text))
        self.setParam('sub_action', subCmd)
        if text:
            self.setParam('sub_action_text', text)

    def setSubCmdExt(self, subCmdExt):
        assert (isinstance(subCmdExt, TodoTask))
        self.setParam('sub_action_ext', subCmdExt)
        return self

    def setSubTextExt(self, subTextExt):
        self.setParam('sub_text_ext', subTextExt)
        return self

    def setSubCmdExtWithText(self, subCmd, text=None):
        assert (isinstance(subCmd, TodoTask))
        assert (text is None or isstring(text))
        self.setParam('sub_action_ext', subCmd)
        if text:
            self.setParam('sub_text_ext', text)

    def addSubCmdExtText(self, text):
        assert (isstring(text))
        self.setParam('sub_action_ext_btn_text', text)
        return self

    def setSubCmdClose(self, subCmd):
        assert (isinstance(subCmd, TodoTask))
        self.setParam('sub_action_close', subCmd)
        return self

    def toDict(self):
        return self._data


# 访问html TodoTask模板
class TodoTaskVisitHtml(TodoTask):
    def __init__(self, url):
        assert (isstring(url))
        super(TodoTaskVisitHtml, self).__init__('rep_sence_activity')
        self.setParam('url', url)


# 购买引导 TodoTask模板
class TodoTaskPayOrder(TodoTask):
    def __init__(self, product=None):
        super(TodoTaskPayOrder, self).__init__('pop_pay_order')
        self.isWinpc = False
        self.isWinpcCharge = False
        if product:
            self.updateParams(TodoTaskHelper.getParamsByProduct(product))


class TodoTaskLessBuyOrder(TodoTask):
    def __init__(self, desc, iconPic, note, product=None):
        super(TodoTaskLessBuyOrder, self).__init__('pop_order')
        self.setParam('desc', desc)
        self.setParam('iconPic', iconPic)
        self.setParam('note', note)
        if product:
            self.setSubCmd(TodoTaskPayOrder(product))


# 发送快速开始 TodoTask模板
class TodoTaskQuickStart(TodoTask):
    def __init__(self, gameId=0, roomId=0, tableId=0, seatId=0):
        super(TodoTaskQuickStart, self).__init__('quick_start')
        self.setParam('gameid', gameId)
        self.setParam('roomid', roomId)
        self.setParam('tableid', tableId)
        self.setParam('seatid', seatId)


# 显示弹窗信息 TodoTask模板
class TodoTaskShowInfo(TodoTask):
    def __init__(self, des='', allow_close=False):
        super(TodoTaskShowInfo, self).__init__('pop_info_wnd')
        if des:
            self.setParam('des', des)
        if allow_close:
            self.setParam('allow_close', allow_close)


# 显示公告信息 TodoTask模板
class TodoTaskAnnounce(TodoTask):
    def __init__(self, announceList):
        super(TodoTaskAnnounce, self).__init__('show_bulletin_board')
        self.setParam('announceList', announceList)


# 显示购买弹窗 TodoTask模板
class TodoTaskOrderShow(TodoTask):
    def __init__(self, desc, note, price, detail):
        super(TodoTaskOrderShow, self).__init__('pop_order_info')
        self.setParam('allow_close', True)
        self.setParam('des', desc)
        self.setParam('note', note)
        self.setParam('price', price)
        self.setParam('detail', detail)

    @classmethod
    def makeByProduct(cls, desc, note, product, buyType=''):
        params = TodoTaskHelper.getParamsByProduct(product)
        ret = TodoTaskOrderShow(desc, note, params['price'], params['tip'])
        payOrder = TodoTaskPayOrder().updateParams(params)
        if buyType:
            payOrder.setParam('buy_type', buyType)
        ret.setSubCmd(payOrder)
        return ret


# 引导购买Ext TodoTask模板
class TodoTaskLottery(TodoTask):
    def __init__(self):
        super(TodoTaskLottery, self).__init__('pop_lottery_wnd')


# 通用的显示中奖/开奖信息的todotask
class TodoTaskShowRewards(TodoTask):
    def __init__(self, rewards):
        super(TodoTaskShowRewards, self).__init__('show_rewards')
        self.setParam('rewards', rewards)


# 进入大厅自建桌
class TodotaskEnterFriendTable(TodoTask):
    def __init__(self):
        super(TodotaskEnterFriendTable, self).__init__('hall_enter_friend_table')


# 30日签到
class TodoTaskCheckin(TodoTask):
    ''' 30日签到'''

    def __init__(self):
        ''' subStore: coin '''
        super(TodoTaskCheckin, self).__init__('pop_checkin_wnd')


# 活动弹窗 TodoTask模板
class TodoTaskActivity(TodoTask):
    def __init__(self):
        super(TodoTaskActivity, self).__init__('pop_active_wnd')

    def setLeft(self, pic_url, subCmd):
        left = {}
        left['pic_url'] = pic_url
        left['sub_action'] = subCmd.toDict()
        return self.setParam('left', left)

    def setRight(self, pic_url, subCmd):
        right = {}
        right['pic_url'] = pic_url
        right['sub_action'] = subCmd.toDict()
        return self.setParam('right', right)

    def setMiddle(self, pic_url, subCmd):
        middle = {}
        middle['pic_url'] = pic_url
        middle['sub_action'] = subCmd.toDict()
        return self.setParam('mid', middle)


class TodoTaskActivityNew(TodoTask):
    def __init__(self, actId):
        assert (actId is None or isstring(actId))
        super(TodoTaskActivityNew, self).__init__('pop_active_wnd')
        if actId is not None:
            self.setParam('actId', actId)


class TodoTaskMonthCheckinNew(TodoTask):
    def __init__(self):
        super(TodoTaskMonthCheckinNew, self).__init__('pop_checkin_wnd')


# 退出弹窗 TodoTask模板
# 废弃，前端从v3.9版本开始不响应此todotask，被hall_exit_remind代替
class TodoTaskExit(TodoTask):
    def __init__(self, type_):
        super(TodoTaskExit, self).__init__('set_exit_wnd')
        self.setParam('type', type_)


# 翻牌弹窗 TodoTask模板
class TodoTaskFlipCard(TodoTask):
    def __init__(self, nlogin, ispop, paddings, remfliptimes, rewards):
        super(TodoTaskFlipCard, self).__init__('flip_card')
        self.setParam('nlogin', nlogin)
        self.setParam('ispop', nlogin)
        self.setParam('paddings', paddings)
        self.setParam('remfliptimes', remfliptimes)
        self.setParam('rewards', rewards)


# 绑定手机弹窗
class TodoTaskBindPhone(TodoTask):
    def __init__(self, info, rewardTip):
        super(TodoTaskBindPhone, self).__init__('bind_phone')
        self.setParam('info', info)
        self.setParam('rewardtip', rewardTip)


class TodoTaskBindPhoneFriend(TodoTask):
    def __init__(self, info, rewardTip):
        super(TodoTaskBindPhoneFriend, self).__init__('bind_phone_friend')
        self.setParam('info', info)
        self.setParam('rewardtip', rewardTip)


# 绑定手机弹窗
class TodoTaskBindSnsId360(TodoTask):
    def __init__(self, info, rewardTip):
        super(TodoTaskBindSnsId360, self).__init__('bind_snsid_360')
        self.setParam('info', info)
        self.setParam('rewardtip', rewardTip)


# 每日领奖弹窗
class TodoTaskNsloginReward(TodoTask):
    def __init__(self, states):
        super(TodoTaskNsloginReward, self).__init__('nslogin_reward')
        self.setParam('rewardstate', states)

    def setMemberInfo(self, isMember, remainDays, memberBonus):
        memberInfo = {
            'isMember': isMember,
            'remainDays': remainDays,
            'memberBonus': memberBonus,
        }
        return self.setParam('memberInfo', memberInfo)


# 通知新手启动资金
class TodoTaskIssueStartChip(TodoTask):
    def __init__(self, startChip, totalChip, pic, tip):
        super(TodoTaskIssueStartChip, self).__init__('issue_start_chip')
        self.setParam('startchip', startChip)
        self.setParam('totalchip', totalChip)
        self.setParam('picurl', pic)
        self.setParam('tip', tip)


# 快速开始提示
class TodoTaskQuickStartTip(TodoTask):
    def __init__(self):
        super(TodoTaskQuickStartTip, self).__init__('quick_start_tip')


class TodoTaskObserve(TodoTask):
    ''' 旁观 '''

    def __init__(self, gameId, roomId, tableId):
        super(TodoTaskObserve, self).__init__('observe')
        self.setParam('gameId', gameId)
        self.setParam('roomId', roomId)
        self.setParam('tableId', tableId)


class TodoTaskLeaveRoom(TodoTask):
    ''' 离开房间 '''

    def __init__(self, gameId, roomId):
        super(TodoTaskLeaveRoom, self).__init__('leave_room')
        self.setParam('gameId', gameId)
        self.setParam('roomId', roomId)


class TodoTaskTriggerEvent(TodoTask):
    def __init__(self, event, params):
        super(TodoTaskTriggerEvent, self).__init__('trigger_event')
        self.setParam('event', event)
        self.setParam('params', params)


class TodoTaskTutorial(TodoTask):
    ''' 新手教学 '''

    def __init__(self):
        super(TodoTaskTutorial, self).__init__('show_tutorial')


class TodoTaskChangeTable(TodoTask):
    ''' 换房间。前端自己知道roomId'''

    def __init__(self, gameId):
        super(TodoTaskChangeTable, self).__init__('change_table')
        self.setParam('gameId', gameId)


class TodoTaskGotoShop(TodoTask):
    ''' 去商城界面'''

    def __init__(self, subStore='coin'):
        ''' subStore: coin '''
        super(TodoTaskGotoShop, self).__init__('rep_sence_shop')
        self.setParam('subStore', subStore)


class TodoTaskGotoFree(TodoTask):
    ''' 去免费福利'''

    def __init__(self):
        super(TodoTaskGotoFree, self).__init__('rep_sence_free')


class TodoTaskPopTip(TodoTask):
    def __init__(self, text=''):
        super(TodoTaskPopTip, self).__init__('pop_tip')
        self.setParam('text', text)


class TodoTaskInviteToGame(TodoTask):
    '''
    邀请去游戏
    note - 邀请内容
    enterParams - 邀请的具体行为
    inviter - 邀请人的uid
    inviterName - 邀请人的名称
    '''

    def __init__(self, inviter, note='', enterParams={}):
        super(TodoTaskInviteToGame, self).__init__('invite_to_game')
        self.setParam('note', note)
        self.setParam('inviter', inviter)
        uds = userdata.getAttrs(inviter, ['purl', 'name'])
        self.setParam('inviterHeadUrl', uds[0])
        self.setParam('inviterName', uds[1])

        subAction = TodoTaskEnterGameNew(enterParams['gameId'], enterParams['enter_param'])
        self.setSubCmd(subAction)


class TodoTaskGotoVip(TodoTask):
    def __init__(self):
        super(TodoTaskGotoVip, self).__init__('rep_sence_vip')


class TodoTaskGotoPromote(TodoTask):
    def __init__(self):
        super(TodoTaskGotoPromote, self).__init__('rep_sence_promote')


class TodoTaskNoop(TodoTask):
    def __init__(self):
        super(TodoTaskNoop, self).__init__('do_nothing')


class TodoTaskVipGotGift(TodoTask):
    def __init__(self, giftLevel, exp, name, desc, giftInfo):
        super(TodoTaskVipGotGift, self).__init__('vip_get_gift')
        self.setParam('level', giftLevel)
        self.setParam('exp', exp)
        self.setParam('name', name)
        self.setParam('desc', desc)
        if giftInfo is not None:
            self.setParam('giftInfo', giftInfo)


class TodoTaskVipLevelUp(TodoTask):
    def __init__(self, vipInfo, desc):
        super(TodoTaskVipLevelUp, self).__init__('vip_level_up')
        self.setParam('vipInfo', vipInfo)
        self.setParam('desc', desc)


class TodotaskFlipCardNew(TodoTask):
    def __init__(self, gameId, roomId, title, desc, tips):
        super(TodotaskFlipCardNew, self).__init__('flip_card_luck')
        self.setParam('gameId', gameId)
        self.setParam('roomId', roomId)
        self.setParam('title', title)
        self.setParam('desc', desc)
        self.setParam('tips', tips)


class TodoTaskEnterGame(TodoTask):
    ''' 进入某个插件游戏
    gameMark: str, 'texas', 'ddz' 等，同 gameList 中的 gameMark
    gameType: any, 游戏类型，比如区分斗牛和百人，估计用处不大了
    gameSpecifyParams: 游戏各自解析用，一般会包含 type, roomId, tableId, seatId 等
    '''

    def __init__(self, gameMark, gameType, **gameSpecifyParams):
        super(TodoTaskEnterGame, self).__init__('enter_game')
        self.setParam('game_mark', gameMark)
        self.setParam('game_type', gameType)
        self.setParam('enter_param', gameSpecifyParams)


class TodoTaskEnterGameNew(TodoTask):
    ''' 进入某个插件游戏
    gameId: 游戏ID，比如6 7 8等
    enterParams: 游戏各自解析用，一般会包含 type, pluginParams
    type枚举
        quickstart: 快速开始
            pluginParams：
                各游戏参数略有不同，大厅透传，包含roomId，tableId，sessionIndex等
        roomlist: 插件游戏的玩法房间列表界面
            pluginParams：
                gameType
        game: 插件游戏的二级子大厅
            pluginParams：无
    '''

    def __init__(self, gameId, enterParams):
        super(TodoTaskEnterGameNew, self).__init__('enter_game')
        self.setParam('gameId', gameId)
        self.setParam('enter_param', enterParams)


class TodoTaskDiZhuEvent(TodoTask):
    '''
    地主内部跳回大厅
    '''

    def __init__(self, event):
        super(TodoTaskDiZhuEvent, self).__init__('trigger_event')
        self.setParam('event', event)


class TodoTaskShareUrl(TodoTask):
    def __init__(self, shareId, shareType, subType,
                 desc, url, tips, title, shareIcon):
        super(TodoTaskShareUrl, self).__init__('share_url')
        self.setParam('id', str(shareId))
        self.setParam('type', shareType)
        self.setParam('subType', subType)
        self.setParam('des', desc)
        self.setParam('url', url)
        self.setParam('tips', tips)
        self.setParam('title', title)
        self.setParam('shareIcon', shareIcon)


class TodoTaskShareGift(TodoTask):
    def __init__(self, shareId, shareLoc, desc, url, title, descUpper, descLower, shareIcon, tips=None):
        super(TodoTaskShareGift, self).__init__('share_gift')
        self.setParam('shareId', str(shareId))
        self.setParam('shareLoc', shareLoc)
        self.setParam('des', desc)
        self.setParam('url', url)
        self.setParam('title', title)
        self.setParam('descUpper', descUpper)
        self.setParam('descLower', descLower)
        self.setParam('shareIcon', shareIcon)
        if tips:
            self.setParam('tips', tips)


class TodoTaskGoldRain(TodoTask):
    def __init__(self, desc=''):
        super(TodoTaskGoldRain, self).__init__('gold_rain')
        self.setParam('desc', desc)


class TodoTaskFirstRecharge(TodoTask):
    def __init__(self, title, imgUrl, payOrder=None, confirm=0, confirmDesc=None, subText=None):
        super(TodoTaskFirstRecharge, self).__init__('pop_first_recharge')
        self.setParam('title', title)
        self.setParam('imgUrl', imgUrl)
        if subText:
            self.setParam('subText', subText)
            self.setParam('sub_action_text', subText)
        if payOrder:
            subCmd = payOrder
            if isinstance(payOrder, TYProduct):
                subCmd = TodoTaskPayOrder(payOrder)
            if confirm:
                confirmDesc = confirmDesc or ''
                if confirmDesc:
                    confirmDesc = strutil.replaceParams(confirmDesc, {
                        'product.displayName': subCmd.getParam('name', ''),
                        'product.price': subCmd.getParam('price', '')
                    })
                info = TodoTaskShowInfo(confirmDesc, True)
                info.setSubCmd(subCmd)
                subCmd = info
            self.setSubCmd(subCmd)


class TodoTaskReceiveFirstRechargeReward(TodoTask):
    def __init__(self):
        super(TodoTaskReceiveFirstRechargeReward, self).__init__('receive_first_recharge')


class TodoTaskFirstRechargeReward(TodoTask):
    def __init__(self, title, imgUrl):
        super(TodoTaskFirstRechargeReward, self).__init__('pop_first_recharge')
        self.setParam('title', title)
        self.setParam('imgUrl', imgUrl)
        self.setSubCmd(TodoTaskReceiveFirstRechargeReward())


class TodoTaskWifikeyPromote(TodoTask):
    def __init__(self):
        super(TodoTaskWifikeyPromote, self).__init__('thirdsdk_promote')


class TodoTaskShowMoreGamePromote(TodoTask):
    def __init__(self):
        super(TodoTaskShowMoreGamePromote, self).__init__('thirdsdk_more_game')


class TodoTaskMiguMusicPromote(TodoTask):
    def __init__(self):
        super(TodoTaskMiguMusicPromote, self).__init__('thirdsdk_migu')


class TodoTaskThirdSDKExtend(TodoTask):
    def __init__(self, action):
        super(TodoTaskThirdSDKExtend, self).__init__('thirdsdk_extend')
        self.setParam('action', action)


class TodoTaskDownloadApkPromote(TodoTask):
    def __init__(self, url):
        super(TodoTaskDownloadApkPromote, self).__init__('download_apk')
        self.setParam('url', url)


class TodoTaskRename(TodoTask):
    def __init__(self, desc):
        super(TodoTaskRename, self).__init__('change_name')
        self.setParam('desc', desc)


class TodoTaskMemberBuy(TodoTask):
    def __init__(self, desc, pic):
        super(TodoTaskMemberBuy, self).__init__('pop_member_buy')
        self.setParam('desc', desc)
        self.setParam('picUrl', pic)


class TodoTaskMemberTry(TodoTask):
    def __init__(self, desc, pic):
        super(TodoTaskMemberTry, self).__init__('pop_member_try')
        self.setParam('desc', desc)
        self.setParam('picUrl', pic)


class TodoTaskRecommendBuy(TodoTask):
    def __init__(self, desc, pic, titlePic, payOrderProduct, payOrderText=None):
        super(TodoTaskRecommendBuy, self).__init__('pop_recommend_buy')
        self.setParam('desc', desc)
        self.setParam('imgUrl', pic)
        self.setParam('titleUrl', titlePic)
        if payOrderProduct:
            self.setSubCmdWithText(TodoTaskPayOrder(payOrderProduct), payOrderText)


class TodoTaskLuckBuy(TodoTask):
    def __init__(self, desc, tip, payOrderProduct, payOrderText=None):
        super(TodoTaskLuckBuy, self).__init__('pop_lucky_buy')
        self.setParam('desc', desc)
        self.setParam('tip', tip)
        if payOrderProduct:
            self.setSubCmdWithText(TodoTaskPayOrder(payOrderProduct), payOrderText)


class TodoTaskWinBuy(TodoTask):
    def __init__(self, desc, tip, payOrderProduct, payOrderText=None):
        super(TodoTaskWinBuy, self).__init__('pop_winer_buy')
        self.setParam('desc', desc)
        self.setParam('tip', tip)
        if payOrderProduct:
            self.setSubCmdWithText(TodoTaskPayOrder(payOrderProduct), payOrderText)


class TodoTaskGotoHelp(TodoTask):
    def __init__(self):
        super(TodoTaskGotoHelp, self).__init__('rep_sence_help')


class TodoTaskFiveStarRating(TodoTask):
    def __init__(self, rateUrl):
        super(TodoTaskFiveStarRating, self).__init__('five_star_rating')
        self.setParam('rateUrl', rateUrl)


class TodoTaskPopFiveStarWnd(TodoTask):
    def __init__(self, desc, rateUrl):
        super(TodoTaskPopFiveStarWnd, self).__init__('pop_five_star_wnd')
        self.setParam('desc', desc)
        if rateUrl:
            self.setSubCmd(TodoTaskFiveStarRating(rateUrl))
        self.setSubCmdExt(TodoTaskGotoHelp())


class TodoTaskGetMemberReward(TodoTask):
    def __init__(self):
        super(TodoTaskGetMemberReward, self).__init__('get_member_reward')


class TodoTaskRepScenePromteDirect(TodoTask):
    def __init__(self):
        super(TodoTaskRepScenePromteDirect, self).__init__('rep_sence_promote_direct')


# 添加一条退出召回信息
class TodoTaskAddExitNotification(TodoTask):
    def __init__(self, dsc, time):
        super(TodoTaskAddExitNotification, self).__init__('add_exit_notification')
        self.setParam('dsc', dsc)
        self.setParam('time', time)


# 打开/下载一个三方应用
class TodoTaskDownloadOrOpenThirdApp(TodoTask):
    def __init__(self, packageName, scheme, downloadUrl, downloadType, appCode, MD5):
        super(TodoTaskDownloadOrOpenThirdApp, self).__init__('download_open_third_app')
        # packageName 在Android里是包名，在IOS里是bundle id
        self.setParam('packageName', packageName)
        # scheme
        self.setParam('scheme', scheme)
        # 下载URL
        self.setParam('downloadUrl', downloadUrl)
        # 下载类型，game是游戏内下载，browser是浏览器下载，只有安卓和IOS越狱渠道可以做到游戏内下载
        self.setParam('downloadType', downloadType)
        # 三方app编码，用于内部统计等
        self.setParam('appCode', appCode)
        # 下载文件的MD5
        self.setParam('MD5', MD5)


# 回传一个消息给后端
class TodoTaskSendMsg(TodoTask):
    def __init__(self, msg):
        super(TodoTaskSendMsg, self).__init__('send_msg')
        self.setParam("msg", msg)


class TodoTaskFactory(TYConfable):
    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        raise NotImplemented()


class TodoTaskGotoCheckinFactory(TodoTaskFactory):
    TYPE_ID = 'hall.goto.checkin'

    def __init__(self):
        super(TodoTaskGotoCheckinFactory, self).__init__()

    def decodeFromDict(self, d):
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskCheckin()


class TodoTaskGotoLotteryFactory(TodoTaskFactory):
    TYPE_ID = 'hall.goto.lottery'

    def __init__(self):
        super(TodoTaskGotoLotteryFactory, self).__init__()

    def decodeFromDict(self, d):
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskLottery()


class TodoTaskGotoShopFactory(TodoTaskFactory):
    TYPE_ID = 'hall.goto.shop'

    def __init__(self):
        super(TodoTaskGotoShopFactory, self).__init__()
        self.subStore = None

    def decodeFromDict(self, d):
        self.subStore = d.get('subStore')
        if not isstring(self.subStore):
            raise TYBizConfException(d, 'TodoTaskGotoShopFactory.subStore must be string')
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskGotoShop(self.subStore)


class TodoTaskGotoFreeFactory(TodoTaskFactory):
    TYPE_ID = 'hall.goto.free'

    def __init__(self):
        super(TodoTaskGotoFreeFactory, self).__init__()

    def decodeFromDict(self, d):
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskGotoFree()


class TodoTaskGotoVipFactory(TodoTaskFactory):
    TYPE_ID = 'hall.goto.vip'

    def __init__(self):
        super(TodoTaskGotoVipFactory, self).__init__()

    def decodeFromDict(self, d):
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskGotoVip()


class TodoTaskGotoPromoteFactory(TodoTaskFactory):
    TYPE_ID = 'hall.goto.promote'

    def __init__(self):
        super(TodoTaskGotoPromoteFactory, self).__init__()

    def decodeFromDict(self, d):
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskGotoPromote()


class TodoTaskWifikeyPromoteFactory(TodoTaskFactory):
    TYPE_ID = 'hall.wifikey.promote'

    def __init__(self):
        super(TodoTaskWifikeyPromoteFactory, self).__init__()

    def decodeFromDict(self, d):
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskWifikeyPromote()


class TodoTaskShowMoreGamePromoteFactory(TodoTaskFactory):
    TYPE_ID = 'hall.showMoreGame.promote'

    def __init__(self):
        super(TodoTaskShowMoreGamePromoteFactory, self).__init__()

    def decodeFromDict(self, d):
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskShowMoreGamePromote()


class TodoTaskMiguMusicPromoteFactory(TodoTaskFactory):
    TYPE_ID = 'hall.migu.music'

    def __init__(self):
        super(TodoTaskMiguMusicPromoteFactory, self).__init__()

    def decodeFromDict(self, d):
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskMiguMusicPromote()


class TodoTaskThirdSDKExtendFactory(TodoTaskFactory):
    TYPE_ID = 'hall.thirdsdk.extend'

    def __init__(self):
        super(TodoTaskThirdSDKExtendFactory, self).__init__()
        self.action = None

    def decodeFromDict(self, d):
        self.action = d.get('action', '')
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskThirdSDKExtend(self.action)


class TodoTaskDownloadPromoteFactory(TodoTaskFactory):
    TYPE_ID = 'hall.download'

    def __init__(self):
        super(TodoTaskDownloadPromoteFactory, self).__init__()
        self.url = None

    def decodeFromDict(self, d):
        self.url = d.get('url', '')
        if not isstring(self.url):
            raise TYBizConfException(d, 'TodoTaskDownloadPromoteFactory.url must be string')
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskDownloadApkPromote(self.url)


class TodoTaskVisitHtmlFactory(TodoTaskFactory):
    TYPE_ID = 'hall.goto.activity'

    def __init__(self):
        super(TodoTaskVisitHtmlFactory, self).__init__()
        self.url = None

    def decodeFromDict(self, d):
        self.url = d.get('url', '')
        if not isstring(self.url):
            raise TYBizConfException(d, 'TodoTaskVisitHtmlFactory.url must be string')
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskVisitHtml(self.url)


class TodoTaskVisitActivityByIDFactory(TodoTaskFactory):
    TYPE_ID = 'hall.goto.activity.byid'

    def __init__(self):
        super(TodoTaskVisitActivityByIDFactory, self).__init__()
        self.actId = None

    def decodeFromDict(self, d):
        self.actId = d.get('actId', '')
        if not isstring(self.actId):
            raise TYBizConfException(d, 'TodoTaskVisitActivityByIDFactory.actId must be string')
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskActivityNew(self.actId)


class TodoTaskEnterGameNewFactory(TodoTaskFactory):
    TYPE_ID = 'hall.goto.enter.game'

    def __init__(self):
        super(TodoTaskEnterGameNewFactory, self).__init__()
        self.gameId = None
        self.enter_param = None

    def decodeFromDict(self, d):
        self.gameId = d.get('gameId')
        self.enter_param = d.get('enter_param')
        if not isinstance(self.gameId, int):
            raise TYBizConfException(d, 'TodoTaskEnterGameNewFactory.gameId must be int')
        if not isinstance(self.enter_param, dict):
            raise TYBizConfException(d, 'TodoTaskEnterGameNewFactory.enter_param must be dict')
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskEnterGameNew(self.gameId, self.enter_param)


class TodoTaskFirstRechargeFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.firstRecharge'

    def __init__(self):
        super(TodoTaskFirstRechargeFactory, self).__init__()
        self.title = None
        self.url = None
        self.payOrder = None
        self.confirm = None
        self.confirmDesc = None
        self.subText = None

    def decodeFromDict(self, d):
        self.title = d.get('title', '')
        if not isstring(self.title):
            raise TYBizConfException(d, 'TodoTaskFirstRechargeFactory.title must be string')
        self.url = d.get('url', '')
        if not isstring(self.url):
            raise TYBizConfException(d, 'TodoTaskFirstRechargeFactory.url must be string')
        self.confirm = d.get('confirm')
        if self.confirm not in (0, 1):
            raise TYBizConfException(d, 'TodoTaskFirstRechargeFactory.confirm must be int in (0,1)')
        self.confirmDesc = d.get('confirmDesc', '')
        if not isstring(self.confirmDesc):
            raise TYBizConfException(d, 'TodoTaskFirstRechargeFactory.confirmDesc must be string')
        self.subText = d.get('subText', '')
        if not isstring(self.subText):
            raise TYBizConfException(d, 'TodoTaskFirstRechargeFactory.subText must be string')
        self.payOrder = d.get('payOrder')
        if not isinstance(self.payOrder, dict):
            raise TYBizConfException(d, 'TodoTaskFirstRechargeFactory.payOrder must be dict')
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        product = self._getProduct(gameId, userId, clientId)
        payOrder = None
        if product:
            payOrder = TodoTaskHelper.makeTodoTaskPayOrder(userId, clientId, product)
        return TodoTaskFirstRecharge(self.title, self.url, payOrder, self.confirm, self.confirmDesc, self.subText)

    def _getProduct(self, gameId, userId, clientId):
        from hall.entity import hallstore
        product, _ = hallstore.findProductByPayOrder(gameId, userId, clientId, self.payOrder)
        if not product:
            raise TYBizException(-1, 'Product not found')
        return product


class TodoTaskReceiveFirstRechargeRewardFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.receiveFirstRechargeReward'

    def __init__(self):
        super(TodoTaskReceiveFirstRechargeRewardFactory, self).__init__()

    def decodeFromDict(self, d):
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskReceiveFirstRechargeReward()


class TodoTaskFirstRechargeRewardFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.firstRechargeReward'

    def __init__(self):
        super(TodoTaskFirstRechargeRewardFactory, self).__init__()
        self.title = None
        self.url = None

    def decodeFromDict(self, d):
        self.title = d.get('title', '')
        if not isstring(self.title):
            raise TYBizConfException(d, 'TodoTaskFirstRechargeRewardFactory.title must be string')
        self.url = d.get('url', '')
        if not isstring(self.url):
            raise TYBizConfException(d, 'TodoTaskFirstRechargeRewardFactory.url must be string')
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskFirstRechargeReward(self.title, self.url)


class TodoTaskPayOrderFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.payOrder'

    def __init__(self):
        super(TodoTaskPayOrderFactory, self).__init__()
        self.payOrder = None

    def decodeFromDict(self, d):
        self.payOrder = d.get('payOrder')
        if not isinstance(self.payOrder, dict):
            raise TYBizConfException(d, 'TodoTaskPayOrderFactory.payOrder must be dict')

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        '''
        如果有符合配置的商品，则返回购买todotask
        如果没有符合配置的商品，外部逻辑需自己处理
        '''
        from hall.entity import hallstore
        product, _ = hallstore.findProductByPayOrder(gameId, userId, clientId, self.payOrder)
        if product:
            return TodoTaskPayOrder(product)
        else:
            ftlog.warn('TodoTaskPayOrderFactory.newTodoTask No suitable product, please check store config. gameId:',
                       gameId
                       , ' userId:', userId
                       , ' clientId:', clientId
                       , ' payOrder:', self.payOrder)

        return None


class TodoTaskBindPhoneFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.bindPhone'

    def __init__(self):
        super(TodoTaskBindPhoneFactory, self).__init__()
        self.info = None
        self.rewardTip = None

    def decodeFromDict(self, d):
        self.info = d.get('info', '为了您的账号安全,请先绑定手机号')
        if not isstring(self.info):
            raise TYBizConfException(d, 'TodoTaskBindPhoneFactory.info must be string')
        self.rewardTip = d.get('rewardTip', '')
        if not isstring(self.rewardTip):
            raise TYBizConfException(d, 'TodoTaskBindPhoneFactory.rewardTip must be string')

    def newTodoTask(self, gameId, userId, clientId, **kwargs):

        return TodoTaskBindPhone(self.info, self.rewardTip)


class TodoTaskIosUpgradeFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.template.iosUpgrade'

    def __init__(self):
        super(TodoTaskIosUpgradeFactory, self).__init__()

    def decodeFromDict(self, d):
        self.desc = d.get('desc', '')
        if not isstring(self.desc):
            raise TYBizConfException(d, 'TodoTaskIosUpgradeFactory.desc must be string')
        self.url = d.get('url', '')
        if not isstring(self.url):
            raise TYBizConfException(d, 'TodoTaskIosUpgradeFactory.url must be string')
        self.subActionText = d.get('subActionText', '确定')
        self.subActionTextExt = d.get('subActionTextExt', '取消')

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        popInfo = TodoTaskShowInfo(self.desc)
        openUrl = TodoTaskDownloadApkPromote(self.url)
        popInfo.setSubCmd(openUrl)
        popInfo.setSubText(self.subActionText)
        popInfo.setSubTextExt(self.subActionTextExt)
        return popInfo


class TodoTaskDailyShareGiftFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.daily.sharegift'

    def __init__(self):
        super(TodoTaskDailyShareGiftFactory, self).__init__()

    def decodeFromDict(self, d):
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        from hall.entity import hallshare
        shareId = hallshare.getShareId('dailyShare', userId, gameId)
        if shareId is None:
            return None
        share = hallshare.findShare(shareId)
        if not share:
            return None
        return share.buildTodotask(gameId, userId, 'dailyShare')


class TodoTaskDailyShareGiftWithShareIDFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.sharegift.with.shareId'

    def __init__(self):
        super(TodoTaskDailyShareGiftWithShareIDFactory, self).__init__()
        self.shareId = None

    def decodeFromDict(self, d):
        self.shareId = d.get('shareId', 0)
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        from hall.entity import hallshare
        share = hallshare.findShare(self.shareId)
        if not share:
            return None
        return share.buildTodotask(gameId, userId, 'dailyShare')


class TodoTaskShowInfoWithShareFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.showInfo.with.share'

    def __init__(self):
        super(TodoTaskShowInfoWithShareFactory, self).__init__()
        self.shareId = None

    def decodeFromDict(self, d):
        self.shareId = d.get('shareId', 0)
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        from hall.entity import hallshare
        share = hallshare.findShare(self.shareId)
        if share:
            shareTodotask = share.buildTodotask(gameId, userId, 'dailyShare')
            if shareTodotask:
                return TodoTaskShowInfo(share.tips).setSubCmd(shareTodotask)
        return None


class TodoTaskShareFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.share'

    def __init__(self):
        super(TodoTaskShareFactory, self).__init__()
        self.shareId = None
        self.shareLoc = None

    def decodeFromDict(self, d):
        self.shareId = d.get('shareId')
        if not isinstance(self.shareId, int):
            raise TYBizConfException(d, 'TodoTaskShareFactory.shareId must be int')
        self.shareLoc = d.get('shareLoc')
        if not isstring(self.shareLoc):
            raise TYBizConfException(d, 'TodoTaskShareFactory.shareLoc must be string')
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        from hall.entity import hallshare
        share = hallshare.findShare(self.shareId)
        if not share:
            return None
        return share.buildTodotask(gameId, userId, self.shareLoc)


class TodoTaskGetMemberRewardFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.getMemberReward'

    def __init__(self):
        super(TodoTaskGetMemberRewardFactory, self).__init__()

    def decodeFromDict(self, d):
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskGetMemberReward()


class TodoTaskPopSimpleInvite(TodoTask):
    def __init__(self):
        super(TodoTaskPopSimpleInvite, self).__init__('pop_create_room_invite')


class TodoTaskPopSimpleInviteFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.simple.invite'

    def __init__(self):
        super(TodoTaskPopSimpleInviteFactory, self).__init__()

    def decodeFromDict(self, d):
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskPopSimpleInvite()


class TodoTaskRepScenePromteDirectFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.repScenePromteDirect'

    def __init__(self):
        super(TodoTaskRepScenePromteDirectFactory, self).__init__()

    def decodeFromDict(self, d):
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskRepScenePromteDirect()


class TodoTaskFiveStarFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.fiveStar'

    def __init__(self):
        super(TodoTaskFiveStarFactory, self).__init__()

    def decodeFromDict(self, d):
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        clientConf = hallconf.getFiveStarClientConf(clientId)
        todotask = None
        if clientConf.get('disable', 0):
            if ftlog.is_debug():
                ftlog.debug('TodoTaskFiveStarFactory userId=', userId,
                            'clientId=', clientId,
                            'clientConf=', clientConf)
        else:
            from hall.entity.fivestarrate import _parseClientId, _channels, _loadFiveStarRate, _canPopFiveStarRate, \
                _canSendPrize
            ver, channelName = _parseClientId(clientId)
            channel = _channels.get(channelName)
            if channel:
                fsRate = _loadFiveStarRate(userId, channel)
                if _canPopFiveStarRate(userId, ver, fsRate, pktimestamp.getCurrentTimestamp()):
                    if 'appendDesc' in channel and _canSendPrize(channel):
                        todotask = TodoTaskPopFiveStarWnd(channel['appendDesc'], channel['rateUrl'])

        return todotask


class TodoTaskThirdAppFactory(TodoTaskFactory):
    TYPE_ID = 'hall.goto.thirdapp'

    def __init__(self):
        super(TodoTaskThirdAppFactory, self).__init__()
        self.packageName = None
        self.scheme = None
        self.downloadUrl = None
        self.downloadType = None
        self.appCode = None
        self.MD5 = None

    def decodeFromDict(self, d):
        self.packageName = d.get('packageName', '')
        if not isstring(self.packageName):
            raise TYBizConfException(d, 'TodoTaskThirdAppFactory.packageName must be string')

        self.scheme = d.get('scheme', '')
        if not isstring(self.scheme):
            raise TYBizConfException(d, 'TodoTaskThirdAppFactory.scheme must be string')

        self.downloadUrl = d.get('downloadUrl')
        if not isstring(self.downloadUrl):
            raise TYBizConfException(d, 'TodoTaskThirdAppFactory.downloadUrl must be string')

        self.downloadType = d.get('downloadType', '')
        if not isstring(self.downloadType):
            raise TYBizConfException(d, 'TodoTaskThirdAppFactory.downloadType must be string')

        self.appCode = d.get('appCode', 0)

        self.MD5 = d.get('MD5', '')
        if not isstring(self.MD5):
            raise TYBizConfException(d, 'TodoTaskThirdAppFactory.MD5 must be string')

        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskDownloadOrOpenThirdApp(self.packageName, self.scheme, self.downloadUrl, self.downloadType,
                                              self.appCode, self.MD5)


class TodoTaskSendMsgFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.sendMsg'

    def __init__(self):
        super(TodoTaskSendMsgFactory, self).__init__()
        self.msg = None

    def decodeFromDict(self, d):
        self.msg = d.get('msg', {})
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskSendMsg(self.msg)


class TodoTaskShowInfoFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.showInfo'

    def __init__(self):
        super(TodoTaskShowInfoFactory, self).__init__()
        self.info = None

        self.subCmdFactory = None
        self.subText = None

        self.subCmdExtFactory = None
        self.subTextExt = None

        self.allowClose = False

    def decodeFromDict(self, d):
        from hall.entity import hallpopwnd
        self.info = d.get('info')
        if not self.info or not isstring(self.info):
            raise TYBizConfException(d, 'TodoTaskShowInfoFactory.info must be not empty string')

        self.subCmdFactory = d.get('subCmd')
        if self.subCmdFactory is not None:
            self.subCmdFactory = hallpopwnd.decodeTodotaskFactoryByDict(self.subCmdFactory)

        self.subText = d.get('subText')

        self.subCmdExtFactory = d.get('subCmdExt')
        if self.subCmdExtFactory is not None:
            self.subCmdExtFactory = hallpopwnd.decodeTodotaskFactoryByDict(self.subCmdExtFactory)

        self.subTextExt = d.get('subTextExt')

        self.allowClose = d.get('allowClose', False)

        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        ret = TodoTaskShowInfo(self.info, self.allowClose)
        if self.subCmdFactory:
            subCmd = self.subCmdFactory.newTodoTask(gameId, userId, clientId, **kwargs)
            if subCmd:
                ret.setSubCmd(subCmd)

        if self.subText:
            ret.setSubText(self.subText)

        if self.subCmdExtFactory:
            cmdExt = self.subCmdExtFactory.newTodoTask(gameId, userId, clientId, **kwargs)
            if cmdExt:
                ret.setSubCmdExt(cmdExt)

        if self.subTextExt:
            ret.setSubTextExt(self.subTextExt)
        return ret


class TodoTaskGeneralFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.general'

    def __init__(self):
        super(TodoTaskGeneralFactory, self).__init__()
        self.action = None
        self.params = None
        self.actions = None

    def decodeFromDict(self, d):
        self.action = d.get('action')
        if not isstring(self.action) or not self.action:
            raise TYBizConfException(d, 'TodoTaskGeneralFactory.action must be string')
        self.params = d.get('params', {})
        self.actions = d.get('actions', [])
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        from hall.entity import hallpopwnd
        ret = TodoTask(self.action)
        if self.params:
            for k, v in self.params.iteritems():
                ret.setParam(k, v)
        if self.actions:
            for action in self.actions:
                name = action.get('name')
                fac = hallpopwnd.decodeTodotaskFactoryByDict(action.get('action'))
                todotask = fac.newTodoTask(gameId, userId, clientId, **kwargs)
                ret.setParam(name, todotask)
        return ret


# 转发事件的todotask工厂
class TodoTaskTriggerEventFactory(TodoTaskFactory):
    TYPE_ID = 'todotask.trigger.event'

    def __init__(self):
        super(TodoTaskTriggerEventFactory, self).__init__()
        self.event = None
        self.params = None

    def decodeFromDict(self, d):
        self.event = d.get('event', 'hall9999')
        self.params = d.get('params', {})
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskTriggerEvent(self.event, self.params)


# 大厅待发红包的todotask工厂
class TodoTaskHallRedEnvelopeSendFactory(TodoTaskFactory):
    TYPE_ID = 'hall.send.tuyoo.red.envelope'

    def __init__(self):
        super(TodoTaskHallRedEnvelopeSendFactory, self).__init__()
        self.type = None

    def decodeFromDict(self, d):
        self.type = d.get('type')

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        gameids = hallconf.getDaShiFenFilter(clientId)
        for gid in gameids:
            shareTask = TYGame(gid).getTuyooRedEnvelopeShareTask(userId, clientId, self.type)
            if ftlog.is_debug():
                ftlog.debug('TodoTaskHallRedEnvelopeSendFactory.newTodoTask gameId:', gid, ' shareTask:', shareTask)

            if shareTask:
                return shareTask
        return None


class TodoTaskShowRewardsFactory(TodoTaskFactory):
    TYPE_ID = 'hall.send.rewards'

    def __init__(self):
        super(TodoTaskShowRewardsFactory, self).__init__()
        self.rewards = None

    def decodeFromDict(self, d):
        rewards = []
        rList = d.get('rewards', [])
        if ftlog.is_debug():
            ftlog.debug('TodoTaskShowRewardsFactory.decodeFromDict rewards:', rewards)

        for r in rList:
            reward = {}
            reward['name'] = r.get('name', '')
            reward['pic'] = r.get('pic', '')
            reward['count'] = r.get('count', 0)
            rewards.append(reward)

        self.rewards = rewards
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodoTaskShowRewards(self.rewards)


class TodoTaskEnterFriendTableFactory(TodoTaskFactory):
    TYPE_ID = 'hall.enter.friendTable'

    def __init__(self):
        super(TodoTaskEnterFriendTableFactory, self).__init__()

    def decodeFromDict(self, d):
        return self

    def newTodoTask(self, gameId, userId, clientId, **kwargs):
        return TodotaskEnterFriendTable()


class TodoTaskRegister(TYConfableRegister):
    _typeid_clz_map = {
        TodoTaskGotoShopFactory.TYPE_ID: TodoTaskGotoShopFactory,
        TodoTaskGotoVipFactory.TYPE_ID: TodoTaskGotoVipFactory,
        TodoTaskGotoPromoteFactory.TYPE_ID: TodoTaskGotoPromoteFactory,
        TodoTaskWifikeyPromoteFactory.TYPE_ID: TodoTaskWifikeyPromoteFactory,
        TodoTaskShowMoreGamePromoteFactory.TYPE_ID: TodoTaskShowMoreGamePromoteFactory,
        TodoTaskMiguMusicPromoteFactory.TYPE_ID: TodoTaskMiguMusicPromoteFactory,
        TodoTaskThirdSDKExtendFactory.TYPE_ID: TodoTaskThirdSDKExtendFactory,
        TodoTaskDownloadPromoteFactory.TYPE_ID: TodoTaskDownloadPromoteFactory,
        TodoTaskVisitHtmlFactory.TYPE_ID: TodoTaskVisitHtmlFactory,
        TodoTaskFirstRechargeFactory.TYPE_ID: TodoTaskFirstRechargeFactory,
        TodoTaskFirstRechargeRewardFactory.TYPE_ID: TodoTaskFirstRechargeRewardFactory,
        TodoTaskPayOrderFactory.TYPE_ID: TodoTaskPayOrderFactory,
        TodoTaskReceiveFirstRechargeRewardFactory.TYPE_ID: TodoTaskReceiveFirstRechargeRewardFactory,
        TodoTaskVisitActivityByIDFactory.TYPE_ID: TodoTaskVisitActivityByIDFactory,
        TodoTaskEnterGameNewFactory.TYPE_ID: TodoTaskEnterGameNewFactory,
        TodoTaskGotoLotteryFactory.TYPE_ID: TodoTaskGotoLotteryFactory,
        TodoTaskGotoCheckinFactory.TYPE_ID: TodoTaskGotoCheckinFactory,
        TodoTaskBindPhoneFactory.TYPE_ID: TodoTaskBindPhoneFactory,
        TodoTaskIosUpgradeFactory.TYPE_ID: TodoTaskIosUpgradeFactory,
        TodoTaskDailyShareGiftFactory.TYPE_ID: TodoTaskDailyShareGiftFactory,
        TodoTaskDailyShareGiftWithShareIDFactory.TYPE_ID: TodoTaskDailyShareGiftWithShareIDFactory,
        TodoTaskGetMemberRewardFactory.TYPE_ID: TodoTaskGetMemberRewardFactory,
        TodoTaskRepScenePromteDirectFactory.TYPE_ID: TodoTaskRepScenePromteDirectFactory,
        TodoTaskFiveStarFactory.TYPE_ID: TodoTaskFiveStarFactory,
        TodoTaskGotoFreeFactory.TYPE_ID: TodoTaskGotoFreeFactory,
        TodoTaskThirdAppFactory.TYPE_ID: TodoTaskThirdAppFactory,
        TodoTaskSendMsgFactory.TYPE_ID: TodoTaskSendMsgFactory,
        TodoTaskGeneralFactory.TYPE_ID: TodoTaskGeneralFactory,
        TodoTaskTriggerEventFactory.TYPE_ID: TodoTaskTriggerEventFactory,
        TodoTaskShowInfoFactory.TYPE_ID: TodoTaskShowInfoFactory,
        TodoTaskShareFactory.TYPE_ID: TodoTaskShareFactory,
        TodoTaskHallRedEnvelopeSendFactory.TYPE_ID: TodoTaskHallRedEnvelopeSendFactory,
        TodoTaskShowInfoWithShareFactory.TYPE_ID: TodoTaskShowInfoWithShareFactory,
        TodoTaskShowRewardsFactory.TYPE_ID: TodoTaskShowRewardsFactory,
        TodoTaskEnterFriendTableFactory.TYPE_ID: TodoTaskEnterFriendTableFactory,
        # 简单的推广邀请
        TodoTaskPopSimpleInviteFactory.TYPE_ID: TodoTaskPopSimpleInviteFactory,
    }


if __name__ == '__main__':
    quick_start = TodoTaskQuickStart(6, 60101)
    info_str = '亲~您太富有了，该去更高级的房间战斗啦！'
    show_info = TodoTaskShowInfo(info_str).setSubCmd(quick_start)

    print [show_info.toDict()]
    print show_info.toDict()