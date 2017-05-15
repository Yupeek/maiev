# -*- coding: utf-8 -*-
import logging

from common.utils import log_all
from nameko.events import EventDispatcher
from nameko.rpc import rpc
from nameko.timer import timer
from service.dependency.rabbitmq import RabbitMq

logger = logging.getLogger(__name__)


class MonitorerRabbitmq(object):
    """
    the monitorer that track rabbitmq stats to
    report performance issues

    public events
    #############

    - metric_updated(): Service

    rcp
    ###

    track(identifier)

    """
    name = 'monitorer_rabbitmq'
    dispatch = EventDispatcher()
    rabbitmq = RabbitMq()
    """
    :type: components.dependency.rabbitmq.RabbitMqApi
    """

    # ####################################################
    #                 EVENTS
    # ####################################################

    # no events

    # ####################################################
    #                 RPC
    # ####################################################

    @rpc
    def track(self, queue_identifier):
        """
        create a service on the valide scaler
        :param service:
        :return:
        """
        logger.debug("will track %s", queue_identifier)

    # ####################################################
    #                     TIMER
    # $###################################################

    @timer(interval=5)
    @log_all
    def print_status(self):

        import pprint

        metrics = self._compute_queue('rpc-producer')
        if metrics is not None:

            logger.debug(pprint.pformat(metrics))
            self.dispatch("metrics_updated", {
                'monitorer': "monitorer_rabbitmq",
                'identifier': 'rpc-producer',
                'metrics': metrics
            })

    # ####################################################
    #                 PRIVATE
    # ####################################################

    def _compute_queue(self, qname):
        data = self.rabbitmq.get_queue_stats(qname, columns='message_stats,messages_ready,consumers')
        if data is None:
            logger.debug("queue %s does not exists", qname)
            return
        try:
            stats_ = data['message_stats']
        except KeyError:
            logger.exception("bad format from rabbitmq data: %r", data)
            raise
        prate, drate = stats_['publish_details']['rate'], stats_['deliver_details']['rate']
        empty_rate = drate - prate
        try:
            latency = data['messages_ready'] / stats_['deliver_details']['rate']
        except ZeroDivisionError:
            latency = None
        return {
            "waiting": data['messages_ready'],
            "latency": latency,
            "rate": empty_rate,
            "call_rate": prate,
            "exec_rate": drate,
            "consumers": data['consumers']
        }
